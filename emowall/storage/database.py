"""SQLite 数据库连接管理器。

职责：
    * 打开 SQLite 连接并设置 PRAGMA（WAL、外键、busy_timeout）
    * 执行建表 DDL（schema v1）
    * 管理 ``PRAGMA user_version`` 作为 schema 版本
    * 提供上下文管理器（``with`` 语句）
    * 连接阶段异常映射为 ``StorageConnectionError``

线程契约：
    连接在构造线程上使用。``check_same_thread=True``（默认）。
    Stage 5 由 ``StorageService``（QThread）独占使用。
    本类不创建线程、不加锁。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .errors import StorageConnectionError

logger = logging.getLogger("emowall.storage")

#: 当前 schema 版本（初始为 1）。
_SCHEMA_VERSION: int = 1

# ---- DDL ----

_CREATE_CONVERSATIONS: str = """\
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)"""

_CREATE_MESSAGES: str = """\
CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id     TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
    role                TEXT NOT NULL
                        CHECK(role IN ('system', 'user', 'assistant')),
    content             TEXT NOT NULL,
    emotion             TEXT,
    emotion_intensity   REAL
                        CHECK(emotion_intensity IS NULL
                              OR (emotion_intensity >= 0.0
                                  AND emotion_intensity <= 1.0)),
    created_at          TEXT NOT NULL
)"""

_CREATE_INDEX_MESSAGES_CONV: str = """\
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
    ON messages(conversation_id)"""

_CREATE_INDEX_CONV_UPDATED: str = """\
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
    ON conversations(updated_at DESC)"""


class Database:
    """SQLite 数据库连接管理器。

    构造时打开连接、设置 PRAGMA、执行建表和迁移。
    ``close()`` 关闭连接。
    支持上下文管理器（``with`` 语句）。

    线程契约：
        连接在构造线程上使用。``check_same_thread=True``（默认）。
        Stage 5 由 ``StorageService``（QThread）独占使用。
    """

    def __init__(self, path: Path) -> None:
        """打开数据库连接，执行建表和迁移。

        Args:
            path: 数据库文件路径。目录不存在时自动创建。

        Raises:
            TypeError: path 不是 Path 实例
            StorageConnectionError: 连接失败（目录不可创建、权限不足等）
        """
        if not isinstance(path, Path):
            raise TypeError(
                f"path 必须是 pathlib.Path，收到 {type(path).__name__}"
            )

        try:
            # 1. 确保父目录存在
            path.parent.mkdir(parents=True, exist_ok=True)

            # 2. 打开连接（check_same_thread=True 为默认值）
            self._conn = sqlite3.connect(str(path))

            # 3. 设置 PRAGMA
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA busy_timeout = 2000")

            # 4. 执行建表 DDL
            self._init_schema()

            # 5. 设置 schema 版本（仅新数据库）
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                self._conn.commit()

            # 6. 标记连接状态
            self._closed = False

            logger.debug("数据库已打开：%s（schema v%d）", path, self.schema_version)

        except sqlite3.ProgrammingError:
            raise  # 编程错误，不映射
        except sqlite3.InterfaceError:
            raise  # 接口错误，不映射
        except sqlite3.OperationalError as exc:
            self._safe_close()
            raise StorageConnectionError(
                f"数据库连接失败（OperationalError）：{path}"
            ) from exc
        except sqlite3.DatabaseError as exc:
            self._safe_close()
            raise StorageConnectionError(
                f"数据库文件损坏或格式不兼容：{path}"
            ) from exc
        except OSError as exc:
            self._safe_close()
            raise StorageConnectionError(
                f"文件系统错误：{path}"
            ) from exc

    # ---- 公共接口 ----

    def close(self) -> None:
        """关闭数据库连接。幂等：多次调用无副作用。

        状态约定（F-04 修复）：
            * **仅当**底层连接成功关闭后才置 ``_closed = True``；
            * 关闭失败（例如非创建线程调用，``check_same_thread=True``
              会抛 ``sqlite3.ProgrammingError``）时异常向上传播，
              ``_closed`` 保持 ``False``，创建线程后续仍可正确关闭；
            * 已关闭（``_closed`` 为真）时再次调用为无操作。

        契约 §5.2.3：``sqlite3.ProgrammingError`` 属于编程错误，不做映射，
        直接向上抛出。

        Raises:
            sqlite3.ProgrammingError: 跨线程关闭或连接已失效时的编程错误
        """
        if getattr(self, "_closed", False):
            return  # 已正常关闭，幂等

        conn = getattr(self, "_conn", None)
        if conn is None:
            # 未成功建立连接（构造早期失败），无资源可释放
            self._closed = True
            return

        # 关闭失败必须传播；仅成功后更新状态。
        # 注：sqlite3 对「已关闭连接」再次 close() 是原生幂等的（不抛异常）。
        conn.close()
        self._closed = True

    @property
    def schema_version(self) -> int:
        """当前 schema 版本（PRAGMA user_version）。

        Raises:
            sqlite3.ProgrammingError: 连接已关闭
        """
        row = self._conn.execute("PRAGMA user_version").fetchone()
        return row[0]

    @property
    def _connection(self) -> sqlite3.Connection:
        """底层 SQLite 连接（私有 API，仅供同包 Repository 内部使用）。

        不属于冻结契约的公共接口。

        Raises:
            sqlite3.ProgrammingError: 连接已关闭时，后续操作自然抛出
        """
        return self._conn

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ---- 内部方法 ----

    def _init_schema(self) -> None:
        """执行建表 DDL 和索引创建。"""
        self._conn.execute(_CREATE_CONVERSATIONS)
        self._conn.execute(_CREATE_MESSAGES)
        self._conn.execute(_CREATE_INDEX_MESSAGES_CONV)
        self._conn.execute(_CREATE_INDEX_CONV_UPDATED)
        self._conn.commit()

    def _safe_close(self) -> None:
        """尽力关闭连接（初始化失败时使用），忽略所有错误。"""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


__all__ = ["Database"]
