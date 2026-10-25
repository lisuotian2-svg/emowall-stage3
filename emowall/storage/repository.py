"""会话与消息的 CRUD 仓库。

职责：
    * 会话（conversations）的创建、查询、重命名、删除
    * 消息（messages）的追加、查询
    * 情绪字段的更新（预留接口，Stage 4 消费）
    * 标题规范化（与 ``_normalize_title()`` 共用）
    * 自动标题生成（第一条用户消息触发）

线程契约：
    继承 ``Database`` 的线程绑定约束。
    每次操作是一个短事务。
    本类不创建线程、不加锁。

事务所有权：
    Repository 对自身写操作拥有事务所有权。
    每次写操作开始前检查是否存在外部活动事务；
    若存在，则拒绝操作以保护调用方的事务边界。
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
import uuid

from .database import Database
from .errors import StorageIntegrityError, StorageIOError, StorageTimestampError
from ._timestamps import UnsupportedTimestamp, timestamp_key
from .models import (
    Conversation,
    MessageRecord,
    VALID_ROLES,
    _normalize_title,
)

logger = logging.getLogger("emowall.storage")


def _utcnow() -> str:
    """返回当前 UTC 时间，ISO-8601 格式，六位微秒精度，``Z`` 后缀。"""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _rollback_preserving_error(conn: sqlite3.Connection, error: Exception) -> None:
    """尽力回滚本次写入，清理失败不能替换首要错误。

    仅在 Repository 已通过外部事务守卫后的异常分支调用。
    回滚失败只附加不含用户正文的诊断，不关闭连接或宣称状态已恢复；
    若事务仍存在，后续写入继续由原有守卫拒绝。
    """
    try:
        conn.rollback()
    except Exception as cleanup_error:
        diagnostic = (
            f"Repository 回滚失败（{type(cleanup_error).__name__}）；"
            "事务清理未确认，连接可能仍有活动事务"
        )
        error.add_note(diagnostic)
        logger.error("%s", diagnostic)


class ConversationRepository:
    """会话与消息的 CRUD 仓库。

    线程契约：继承 ``Database`` 的线程绑定约束。
    每次操作是一个短事务。
    """

    def __init__(self, db: Database) -> None:
        """绑定到已打开的数据库。

        Args:
            db: 已打开的 ``Database`` 实例。

        Raises:
            TypeError: ``db`` 不是 ``Database`` 实例
        """
        if not isinstance(db, Database):
            raise TypeError(
                f"db 必须是 Database 实例，收到 {type(db).__name__}"
            )
        self._db = db

    # ---- 内部辅助 ----

    def _conn(self) -> sqlite3.Connection:
        """获取底层 SQLite 连接（私有访问）。"""
        return self._db._connection

    def _ensure_no_external_transaction(self) -> None:
        """确保没有外部活动事务。

        如果连接上已有活动事务（非本 Repository 发起），
        抛出 ``sqlite3.ProgrammingError`` 以保护调用方的事务边界。
        这是项目负责人批准的调用方误用分类，不执行 SQL 或结束外部事务。

        Raises:
            sqlite3.ProgrammingError: 存在外部活动事务
        """
        conn = self._conn()
        if conn.in_transaction:
            raise sqlite3.ProgrammingError(
                "Repository 无法在外部活动事务内执行操作；"
                "请确保调用方未持有未提交的事务"
            )

    # ---- 会话 CRUD ----

    def create(self, *, title: str, model: str) -> Conversation:
        """创建新会话。

        标题规则（与 ``rename()`` / ``append_message()`` 自动标题共用）：
            1. ``strip()`` 去除首尾空白；
            2. 空串或纯空白 → ``"新会话"``；
            3. ``len(title) > 20`` → ``title[:17] + "..."``（总计 20 个 Python 字符）；
            4. 否则原样使用。

        Args:
            title: 会话标题（任意字符串；空/空白回退为"新会话"，超长截断）
            model: 使用的模型名（非空字符串）

        Returns:
            新创建的 ``Conversation``（含生成的 UUID 和时间戳）

        Raises:
            ValueError: ``model`` 为空串或纯空白
            StorageIOError: 写入失败
            sqlite3.ProgrammingError: 存在外部活动事务
        """
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model 必须是非空字符串")

        self._ensure_no_external_transaction()

        conv_id = str(uuid.uuid4())
        now = _utcnow()
        normalized_title = _normalize_title(title)

        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO conversations (id, title, model, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, normalized_title, model.strip(), now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIntegrityError(f"创建会话失败：{exc}") from exc
        except sqlite3.OperationalError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库操作失败：{exc}") from exc
        except (sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 契约 §5.2.3：回滚本次写入，原样传播编程错误
        except sqlite3.DatabaseError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"文件系统错误：{exc}") from exc

        logger.debug("创建会话：%s", conv_id)
        return Conversation(
            id=conv_id,
            title=normalized_title,
            model=model.strip(),
            created_at=now,
            updated_at=now,
        )

    def list_recent(self, limit: int = 50) -> list[Conversation]:
        """List all safely comparable conversations by real UTC instant.

        Every candidate ``updated_at`` from one read snapshot is validated
        before sorting and applying ``limit``. Any uncomparable record raises
        ``StorageTimestampError`` with all affected IDs, leaving the database
        and connection available for targeted read-only recovery.

        Raises:
            ValueError: ``limit`` is not a positive integer
            StorageTimestampError: at least one timestamp cannot be compared
            StorageIOError: SQLite or filesystem read failure
        """
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"limit 必须是正整数，收到 {limit}")

        conn = self._conn()
        cursor = None
        try:
            # One complete SELECT/fetch establishes the candidate snapshot.
            # Parsing and ordering do not ask SQLite to guess an ISO grammar.
            cursor = conn.execute(
                "SELECT rowid, id, title, model, created_at, updated_at "
                "FROM conversations"
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError as exc:
            raise StorageIOError(f"查询失败：{exc}") from exc
        except sqlite3.ProgrammingError:
            raise  # 编程错误与线程/连接误用原样传播
        except sqlite3.InterfaceError:
            raise
        except sqlite3.DatabaseError as exc:
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            raise StorageIOError(f"文件系统错误：{exc}") from exc
        finally:
            if cursor is not None:
                cursor.close()

        sortable: list[tuple[tuple[int, int, str], tuple]] = []
        invalid: dict[str, tuple[str, Exception | None]] = {}
        for row in rows:
            conversation_id = str(row[1])
            try:
                key = timestamp_key(row[5])
            except UnsupportedTimestamp:
                invalid[conversation_id] = ("unsupported", None)
            except (ValueError, OverflowError) as exc:
                invalid[conversation_id] = ("invalid", exc)
            else:
                sortable.append((key, row))

        if invalid:
            ids = tuple(sorted(invalid))
            kinds = {kind for kind, _ in invalid.values()}
            if kinds == {"invalid"}:
                category = "无效"
            elif kinds == {"unsupported"}:
                category = "不支持或无法识别"
            else:
                category = "无效或不支持"
            error = StorageTimestampError(
                f"无法安全排序最近会话：{len(ids)} 条记录的 updated_at {category}",
                conversation_ids=ids,
            )
            cause = next((invalid[cid][1] for cid in ids if invalid[cid][1] is not None), None)
            if cause is not None:
                raise error from cause
            raise error

        sortable.sort(key=lambda item: (*item[0], item[1][0]), reverse=True)
        return [
            Conversation(
                id=row[1],
                title=row[2],
                model=row[3],
                created_at=row[4],
                updated_at=row[5],
            )
            for _, row in sortable[:limit]
        ]

    def get(self, conversation_id: str) -> Conversation | None:
        """按 ID 查找会话。

        Returns:
            ``Conversation`` 或 ``None``（不存在时）

        Raises:
            StorageIOError: 查询失败
        """
        conn = self._conn()
        try:
            cursor = conn.execute(
                "SELECT id, title, model, created_at, updated_at "
                "FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            row = cursor.fetchone()
        except sqlite3.OperationalError as exc:
            raise StorageIOError(f"查询失败：{exc}") from exc
        except sqlite3.ProgrammingError:
            raise  # 契约 §5.2.3：编程错误不映射
        except sqlite3.InterfaceError:
            raise  # 契约 §5.2.3：接口错误不映射
        except sqlite3.DatabaseError as exc:
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            raise StorageIOError(f"文件系统错误：{exc}") from exc

        if row is None:
            return None

        return Conversation(
            id=row[0],
            title=row[1],
            model=row[2],
            created_at=row[3],
            updated_at=row[4],
        )

    def rename(self, conversation_id: str, title: str) -> None:
        """重命名会话。

        标题规则与 ``create()`` 一致。

        Args:
            conversation_id: 会话 UUID
            title: 新标题

        Raises:
            StorageIntegrityError: ``conversation_id`` 不存在
            StorageIOError: 写入失败
            sqlite3.ProgrammingError: 存在外部活动事务
        """
        self._ensure_no_external_transaction()

        normalized_title = _normalize_title(title)
        now = _utcnow()

        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (normalized_title, now, conversation_id),
            )
            if cursor.rowcount == 0:
                raise StorageIntegrityError(
                    f"会话不存在：{conversation_id}"
                )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIntegrityError(f"重命名失败：{exc}") from exc
        except sqlite3.OperationalError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库操作失败：{exc}") from exc
        except (sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 契约 §5.2.3：回滚本次写入，原样传播编程错误
        except sqlite3.DatabaseError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"文件系统错误：{exc}") from exc
        except StorageIntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 保留业务异常，结束本次 UPDATE 启动的事务

        logger.debug("重命名会话：%s", conversation_id)

    def delete(self, conversation_id: str) -> None:
        """删除会话及其级联删除消息。

        会话不存在时静默（幂等）。

        Raises:
            StorageIntegrityError: 删除违反数据库完整性约束
            StorageIOError: 删除失败
            sqlite3.ProgrammingError: 存在外部活动事务
        """
        self._ensure_no_external_transaction()

        conn = self._conn()
        try:
            conn.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIntegrityError(f"删除失败：{exc}") from exc
        except sqlite3.OperationalError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"删除失败：{exc}") from exc
        except (sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 契约 §5.2.3：回滚本次写入，原样传播编程错误
        except sqlite3.DatabaseError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"文件系统错误：{exc}") from exc

        logger.debug("删除会话：%s", conversation_id)

    # ---- 消息 CRUD ----

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        emotion: str | None = None,
        emotion_intensity: float | None = None,
    ) -> MessageRecord:
        """追加一条消息到会话。

        副作用：
            * 更新会话的 ``updated_at`` 为当前 UTC 时间；
            * 自动标题生成：当 ``role == "user"`` 且该会话尚无 user 消息时，
              用 ``content`` 生成会话标题，规则与 ``create()`` 一致。
              此操作与消息写入在同一事务内。

        Args:
            conversation_id: 会话 UUID（必须已存在）
            role: ``"system"`` | ``"user"`` | ``"assistant"``（必须校验）
            content: 消息文本（可为空串）
            emotion: 情绪标签名称（可选；Stage 4 产出，Stage 3 仅存储）
            emotion_intensity: 情绪强度（可选；非 None 时 ∈ [0.0, 1.0]）

        Returns:
            新创建的 ``MessageRecord``；**id 保证非 None**

        Raises:
            StorageIntegrityError: ``conversation_id`` 不存在（外键违规）
            ValueError: ``role`` 不在合法集合中；
                        或 ``emotion_intensity`` 非 None 且不在 [0.0, 1.0] 内
            StorageIOError: 写入失败
            sqlite3.ProgrammingError: 存在外部活动事务
        """
        # 参数校验
        if role not in VALID_ROLES:
            raise ValueError(
                f"role 必须是 {VALID_ROLES} 之一，收到 {role!r}"
            )
        if emotion_intensity is not None:
            if not isinstance(emotion_intensity, (int, float)):
                raise TypeError("emotion_intensity 必须是 float 或 None")
            if not (0.0 <= emotion_intensity <= 1.0):
                raise ValueError(
                    f"emotion_intensity 必须在 [0.0, 1.0] 内，收到 {emotion_intensity}"
                )

        self._ensure_no_external_transaction()

        now = _utcnow()
        conn = self._conn()

        try:
            # 检查是否为第一条用户消息（用于自动标题）
            is_first_user_msg = False
            if role == "user":
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM messages "
                    "WHERE conversation_id = ? AND role = 'user'",
                    (conversation_id,),
                )
                count = cursor.fetchone()[0]
                is_first_user_msg = (count == 0)

            # 插入消息
            conn.execute(
                "INSERT INTO messages "
                "(conversation_id, role, content, emotion, emotion_intensity, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, role, content, emotion, emotion_intensity, now),
            )
            msg_id = conn.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]

            # 更新会话的 updated_at（以及可能的标题）
            if is_first_user_msg:
                new_title = _normalize_title(content)
                conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (new_title, now, conversation_id),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now, conversation_id),
                )

            conn.commit()
        except sqlite3.IntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIntegrityError(
                f"外键约束失败：conversation_id={conversation_id}"
            ) from exc
        except sqlite3.OperationalError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库操作失败：{exc}") from exc
        except (sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 契约 §5.2.3：回滚本次写入，原样传播编程错误
        except sqlite3.DatabaseError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"文件系统错误：{exc}") from exc

        logger.debug(
            "追加消息：id=%s, 会话=%s, role=%s", msg_id, conversation_id, role
        )
        return MessageRecord(
            id=int(msg_id),
            conversation_id=conversation_id,
            role=role,
            content=content,
            emotion=emotion,
            emotion_intensity=emotion_intensity,
            created_at=now,
        )

    def list_messages(
        self,
        conversation_id: str,
        limit: int | None = None,
    ) -> list[MessageRecord]:
        """列出会话消息（按 ``id`` 正序，即插入顺序）。

        Args:
            conversation_id: 会话 UUID
            limit: 最大返回数；``None`` 表示返回全部消息。
                   **注意**：``limit=None`` 时，超长会话会一次性加载全部记录到内存。

        Returns:
            ``MessageRecord`` 列表（可能为空；会话不存在时也返回空列表）

        Raises:
            ValueError: ``limit`` 不是 None 且 ``limit <= 0``
            StorageIOError: 查询失败
        """
        if limit is not None:
            if not isinstance(limit, int) or limit <= 0:
                raise ValueError(f"limit 必须是正整数或 None，收到 {limit}")

        conn = self._conn()
        try:
            if limit is None:
                cursor = conn.execute(
                    "SELECT id, conversation_id, role, content, emotion, "
                    "emotion_intensity, created_at FROM messages "
                    "WHERE conversation_id = ? ORDER BY id ASC",
                    (conversation_id,),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, conversation_id, role, content, emotion, "
                    "emotion_intensity, created_at FROM messages "
                    "WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
                    (conversation_id, limit),
                )
            rows = cursor.fetchall()
        except sqlite3.OperationalError as exc:
            raise StorageIOError(f"查询失败：{exc}") from exc
        except sqlite3.ProgrammingError:
            raise  # 契约 §5.2.3：编程错误不映射
        except sqlite3.InterfaceError:
            raise  # 契约 §5.2.3：接口错误不映射
        except sqlite3.DatabaseError as exc:
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            raise StorageIOError(f"文件系统错误：{exc}") from exc

        return [
            MessageRecord(
                id=row[0],
                conversation_id=row[1],
                role=row[2],
                content=row[3],
                emotion=row[4],
                emotion_intensity=row[5],
                created_at=row[6],
            )
            for row in rows
        ]

    # ---- 预留接口：情绪更新 ----

    def update_message_emotion(
        self,
        message_id: int,
        *,
        emotion: str,
        emotion_intensity: float,
    ) -> MessageRecord:
        """更新已有消息的情绪分析结果。

        状态：拟定契约（Stage 3 实现，Stage 4 消费）。

        事务：单条 UPDATE 语句，自动提交。
        在提交前完成返回记录的读取，保证原子性。
        成功后返回更新后的完整 ``MessageRecord``（新 frozen 实例）。

        Args:
            message_id: 消息行 ID（必须 > 0）
            emotion: 情绪标签名称（非空字符串；如 ``"happy"``、``"calm"``）
            emotion_intensity: 情绪强度，必须在 [0.0, 1.0] 内

        Returns:
            更新后的 ``MessageRecord``（frozen 新实例；id 保证非 None）

        Raises:
            StorageIntegrityError: ``message_id`` 不存在于 messages 表
            ValueError: ``emotion`` 为空串/纯空白；
                        ``emotion_intensity`` 不在 [0.0, 1.0]；
                        ``message_id <= 0``
            StorageIOError: 写入失败
            sqlite3.ProgrammingError: 存在外部活动事务
        """
        # 参数校验
        if not isinstance(message_id, int) or message_id <= 0:
            raise ValueError(f"message_id 必须是正整数，收到 {message_id}")
        if not isinstance(emotion, str) or not emotion.strip():
            raise ValueError("emotion 必须是非空字符串")
        if not isinstance(emotion_intensity, (int, float)):
            raise TypeError("emotion_intensity 必须是 float")
        if not (0.0 <= emotion_intensity <= 1.0):
            raise ValueError(
                f"emotion_intensity 必须在 [0.0, 1.0] 内，收到 {emotion_intensity}"
            )

        self._ensure_no_external_transaction()

        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE messages SET emotion = ?, emotion_intensity = ? "
                "WHERE id = ?",
                (emotion.strip(), emotion_intensity, message_id),
            )
            if cursor.rowcount == 0:
                raise StorageIntegrityError(
                    f"消息不存在：message_id={message_id}"
                )

            # 在提交前读取更新后的记录，保证原子性
            cursor = conn.execute(
                "SELECT id, conversation_id, role, content, emotion, "
                "emotion_intensity, created_at FROM messages WHERE id = ?",
                (message_id,),
            )
            row = cursor.fetchone()

            conn.commit()
        except sqlite3.IntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIntegrityError(f"更新失败：{exc}") from exc
        except sqlite3.OperationalError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库操作失败：{exc}") from exc
        except (sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 契约 §5.2.3：回滚本次写入，原样传播编程错误
        except sqlite3.DatabaseError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"数据库错误：{exc}") from exc
        except OSError as exc:
            _rollback_preserving_error(conn, exc)
            raise StorageIOError(f"文件系统错误：{exc}") from exc
        except StorageIntegrityError as exc:
            _rollback_preserving_error(conn, exc)
            raise  # 已处理

        logger.debug(
            "更新消息情绪：id=%s", message_id
        )
        return MessageRecord(
            id=row[0],
            conversation_id=row[1],
            role=row[2],
            content=row[3],
            emotion=row[4],
            emotion_intensity=row[5],
            created_at=row[6],
        )


__all__ = ["ConversationRepository"]
