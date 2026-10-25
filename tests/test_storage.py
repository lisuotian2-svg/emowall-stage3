"""Stage 3 存储层测试。

本文件覆盖 ``emowall/storage`` 模块的完整测试集，按契约 v1.2 §7.5 验收清单组织：
    * 异常层级（§7.1 架构兼容性）
    * 数据模型（§7.2 接口完整性）
    * 标题截断策略（§7.5.1）
    * Database 连接管理（Task 3 实现后填充）
    * Repository CRUD 与消息管理（Task 4 实现后填充）
    * 预留接口 update_message_emotion()（Task 4 实现后填充）
    * 异常映射（Task 3/4 实现后填充）
    * 边界条件与数据完整性（Task 3/4 实现后填充）

当前阶段（Task 1 + Task 2）：仅含异常层级和数据模型测试。
"""

from __future__ import annotations

import pytest

from emowall.storage.errors import (
    StorageConnectionError,
    StorageError,
    StorageIntegrityError,
    StorageIOError,
)
from emowall.storage.models import (
    MAX_TITLE_CHARS,
    VALID_ROLES,
    Conversation,
    MessageRecord,
    _normalize_title,
)


# ============================================================================
# Task 1: 异常层级测试
# ============================================================================


class TestExceptionHierarchy:
    """异常层级结构和继承关系测试。"""

    def test_storage_error_is_exception(self) -> None:
        assert issubclass(StorageError, Exception)

    def test_connection_error_inherits_storage_error(self) -> None:
        assert issubclass(StorageConnectionError, StorageError)

    def test_integrity_error_inherits_storage_error(self) -> None:
        assert issubclass(StorageIntegrityError, StorageError)

    def test_io_error_inherits_storage_error(self) -> None:
        assert issubclass(StorageIOError, StorageError)

    def test_subclasses_are_siblings_not_parents(self) -> None:
        """三个子类互不继承。"""
        assert not issubclass(StorageConnectionError, StorageIntegrityError)
        assert not issubclass(StorageConnectionError, StorageIOError)
        assert not issubclass(StorageIntegrityError, StorageConnectionError)
        assert not issubclass(StorageIntegrityError, StorageIOError)
        assert not issubclass(StorageIOError, StorageConnectionError)
        assert not issubclass(StorageIOError, StorageIntegrityError)

    def test_storage_error_does_not_inherit_ai_or_config_error(self) -> None:
        """StorageError 与 AIError、ConfigError 平级，不继承彼此。"""
        from emowall.ai.errors import AIError
        from emowall.config.errors import ConfigError

        assert not issubclass(StorageError, AIError)
        assert not issubclass(StorageError, ConfigError)
        assert not issubclass(AIError, StorageError)
        assert not issubclass(ConfigError, StorageError)

    def test_catch_base_catches_all_subclasses(self) -> None:
        """捕获 StorageError 可以兜住所有子类。"""
        for exc_class in (StorageConnectionError, StorageIntegrityError, StorageIOError):
            with pytest.raises(StorageError):
                raise exc_class("test")

    def test_exception_message_preserved(self) -> None:
        msg = "连接失败：权限不足"
        exc = StorageConnectionError(msg)
        assert str(exc) == msg

    def test_exception_cause_can_be_set(self) -> None:
        """所有 StorageError 支持异常链（保留 __cause__）。"""
        import sqlite3

        original = sqlite3.OperationalError("disk I/O error")
        exc = StorageIOError("写入失败")
        exc.__cause__ = original
        assert exc.__cause__ is original

    def test_raise_from_preserves_cause(self) -> None:
        """raise ... from ... 正确保留 __cause__。"""
        import sqlite3

        original = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        try:
            try:
                raise original
            except sqlite3.IntegrityError as inner:
                raise StorageIntegrityError("外键约束失败") from inner
        except StorageIntegrityError as exc:
            assert exc.__cause__ is original


# ============================================================================
# Task 2: 数据模型测试
# ============================================================================


class TestConversation:
    """Conversation 冻结数据模型测试。"""

    def test_conversation_is_frozen(self) -> None:
        conv = Conversation(
            id="550e8400-e29b-41d4-a716-446655440000",
            title="测试会话",
            model="qwen3:8b",
            created_at="2026-10-24T00:00:00Z",
            updated_at="2026-10-24T00:00:00Z",
        )
        with pytest.raises(AttributeError):
            conv.title = "修改"  # type: ignore[misc]

    def test_conversation_fields_accessible(self) -> None:
        conv = Conversation(
            id="550e8400-e29b-41d4-a716-446655440000",
            title="测试会话",
            model="qwen3:8b",
            created_at="2026-10-24T00:00:00Z",
            updated_at="2026-10-24T00:01:00Z",
        )
        assert conv.id == "550e8400-e29b-41d4-a716-446655440000"
        assert conv.title == "测试会话"
        assert conv.model == "qwen3:8b"
        assert conv.created_at == "2026-10-24T00:00:00Z"
        assert conv.updated_at == "2026-10-24T00:01:00Z"

    def test_conversation_equality(self) -> None:
        kwargs = dict(
            id="550e8400-e29b-41d4-a716-446655440000",
            title="测试会话",
            model="qwen3:8b",
            created_at="2026-10-24T00:00:00Z",
            updated_at="2026-10-24T00:00:00Z",
        )
        assert Conversation(**kwargs) == Conversation(**kwargs)  # type: ignore[arg-type]

    def test_conversation_is_hashable(self) -> None:
        conv = Conversation(
            id="550e8400-e29b-41d4-a716-446655440000",
            title="测试会话",
            model="qwen3:8b",
            created_at="2026-10-24T00:00:00Z",
            updated_at="2026-10-24T00:00:00Z",
        )
        assert isinstance(hash(conv), int)
        # frozen dataclass 可以放入 set
        s = {conv}
        assert conv in s


class TestMessageRecord:
    """MessageRecord 冻结数据模型测试。"""

    def test_message_record_is_frozen(self) -> None:
        msg = MessageRecord(
            id=1,
            conversation_id="550e8400-e29b-41d4-a716-446655440000",
            role="user",
            content="你好",
            emotion=None,
            emotion_intensity=None,
            created_at="2026-10-24T00:00:00Z",
        )
        with pytest.raises(AttributeError):
            msg.content = "修改"  # type: ignore[misc]

    def test_message_record_with_emotion(self) -> None:
        msg = MessageRecord(
            id=1,
            conversation_id="550e8400-e29b-41d4-a716-446655440000",
            role="user",
            content="你好",
            emotion="happy",
            emotion_intensity=0.8,
            created_at="2026-10-24T00:00:00Z",
        )
        assert msg.emotion == "happy"
        assert msg.emotion_intensity == 0.8

    def test_message_record_id_none_for_new(self) -> None:
        """新建消息时 id 为 None（由 Repository 返回时填充）。"""
        msg = MessageRecord(
            id=None,
            conversation_id="550e8400-e29b-41d4-a716-446655440000",
            role="user",
            content="你好",
            emotion=None,
            emotion_intensity=None,
            created_at="2026-10-24T00:00:00Z",
        )
        assert msg.id is None

    def test_message_record_empty_content(self) -> None:
        """content 允许空串。"""
        msg = MessageRecord(
            id=1,
            conversation_id="550e8400-e29b-41d4-a716-446655440000",
            role="assistant",
            content="",
            emotion=None,
            emotion_intensity=None,
            created_at="2026-10-24T00:00:00Z",
        )
        assert msg.content == ""

    def test_message_record_is_hashable(self) -> None:
        msg = MessageRecord(
            id=1,
            conversation_id="550e8400-e29b-41d4-a716-446655440000",
            role="user",
            content="你好",
            emotion=None,
            emotion_intensity=None,
            created_at="2026-10-24T00:00:00Z",
        )
        assert isinstance(hash(msg), int)


# ============================================================================
# Task 2: 标题规范化测试（§7.5.1）
# ============================================================================


class TestNormalizeTitle:
    """_normalize_title() 标题截断策略测试。"""

    def test_empty_string_returns_default(self) -> None:
        assert _normalize_title("") == "新会话"

    def test_pure_whitespace_returns_default(self) -> None:
        assert _normalize_title("   ") == "新会话"
        assert _normalize_title("\t\n") == "新会话"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _normalize_title("  短标题  ") == "短标题"

    def test_short_title_unchanged(self) -> None:
        assert _normalize_title("短标题") == "短标题"

    def test_exactly_max_chars_unchanged(self) -> None:
        """恰好 20 字符不截断。"""
        title = "a" * MAX_TITLE_CHARS
        assert _normalize_title(title) == title
        assert len(_normalize_title(title)) == MAX_TITLE_CHARS

    def test_one_over_max_chars_truncated(self) -> None:
        """21 字符 → 前 17 + '...' = 20 字符。"""
        title = "a" * (MAX_TITLE_CHARS + 1)
        result = _normalize_title(title)
        assert result == "a" * 17 + "..."
        assert len(result) == MAX_TITLE_CHARS

    def test_long_title_truncated_to_20(self) -> None:
        title = "这是一段很长的会话标题用于测试截断功能，超过二十"
        result = _normalize_title(title)
        assert len(result) == MAX_TITLE_CHARS
        assert result.endswith("...")

    def test_truncation_preserves_prefix(self) -> None:
        title = "abcdefghijklmnopqrstu"  # 21 chars
        result = _normalize_title(title)
        assert result == "abcdefghijklmnopq..."  # 17 + "..."

    def test_strip_then_truncate(self) -> None:
        """先 strip 再截断。"""
        title = "  " + "a" * 25 + "  "
        result = _normalize_title(title)
        assert len(result) == MAX_TITLE_CHARS
        assert result == "a" * 17 + "..."

    def test_max_title_chars_constant(self) -> None:
        assert MAX_TITLE_CHARS == 20


# ============================================================================
# Task 2: 合法角色集合测试
# ============================================================================


class TestValidRoles:
    """VALID_ROLES 常量测试。"""

    def test_valid_roles_contains_system(self) -> None:
        assert "system" in VALID_ROLES

    def test_valid_roles_contains_user(self) -> None:
        assert "user" in VALID_ROLES

    def test_valid_roles_contains_assistant(self) -> None:
        assert "assistant" in VALID_ROLES

    def test_valid_roles_has_exactly_three(self) -> None:
        assert len(VALID_ROLES) == 3

    def test_valid_roles_is_frozenset(self) -> None:
        assert isinstance(VALID_ROLES, frozenset)


# ============================================================================
# Task 3: Database 连接管理测试
# ============================================================================

import sqlite3
import threading
from pathlib import Path

from emowall.storage.database import Database


class TestDatabaseOpenClose:
    """Database 正常打开与关闭。"""

    def test_open_creates_database_file(self, workdir: Path) -> None:
        db_path = workdir / "test.db"
        db = Database(db_path)
        try:
            assert db_path.exists()
        finally:
            db.close()

    def test_schema_version_is_one(self, workdir: Path) -> None:
        db = Database(workdir / "test.db")
        try:
            assert db.schema_version == 1
        finally:
            db.close()

    def test_close_is_idempotent(self, workdir: Path) -> None:
        db = Database(workdir / "test.db")
        db.close()
        db.close()  # 第二次调用不抛异常
        db.close()  # 第三次也不抛

    def test_context_manager(self, workdir: Path) -> None:
        db_path = workdir / "test.db"
        with Database(db_path) as db:
            assert db.schema_version == 1
        # 退出 with 后连接已关闭

    def test_context_manager_closes_on_exception(self, workdir: Path) -> None:
        db_path = workdir / "test.db"
        db_ref: Database | None = None
        with pytest.raises(RuntimeError):
            with Database(db_path) as db:
                db_ref = db
                raise RuntimeError("模拟异常")
        assert db_ref is not None
        # 关闭后使用应抛 ProgrammingError
        with pytest.raises(sqlite3.ProgrammingError):
            db_ref.schema_version  # noqa: B018


class TestDatabaseSchema:
    """数据库 Schema 初始化验证。"""

    def test_conversations_table_exists(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
            ).fetchone()
            assert row is not None
            assert row[0] == "conversations"

    def test_messages_table_exists(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            ).fetchone()
            assert row is not None
            assert row[0] == "messages"

    def test_conversations_columns(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            cols = db._connection.execute("PRAGMA table_info(conversations)").fetchall()
            col_names = {row[1] for row in cols}
            assert col_names == {"id", "title", "model", "created_at", "updated_at"}

    def test_messages_columns(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            cols = db._connection.execute("PRAGMA table_info(messages)").fetchall()
            col_names = {row[1] for row in cols}
            assert col_names == {
                "id", "conversation_id", "role", "content",
                "emotion", "emotion_intensity", "created_at",
            }

    def test_messages_autoincrement(self, workdir: Path) -> None:
        """messages.id 是 AUTOINCREMENT。"""
        with Database(workdir / "test.db") as db:
            row = db._connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'"
            ).fetchone()
            assert "AUTOINCREMENT" in row[0]

    def test_index_messages_conversation_id(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_messages_conversation_id'"
            ).fetchone()
            assert row is not None

    def test_index_conversations_updated_at(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_conversations_updated_at'"
            ).fetchone()
            assert row is not None


class TestDatabasePRAGMAs:
    """PRAGMA 设置验证。"""

    def test_journal_mode_wal(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute("PRAGMA journal_mode").fetchone()
            assert row[0].lower() == "wal"

    def test_foreign_keys_on(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute("PRAGMA foreign_keys").fetchone()
            assert row[0] == 1

    def test_busy_timeout_2000(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            row = db._connection.execute("PRAGMA busy_timeout").fetchone()
            assert row[0] == 2000


class TestDatabaseExceptions:
    """连接阶段异常映射测试（§5.2.1）。"""

    def test_invalid_path_raises_storage_connection_error(self, workdir: Path) -> None:
        """用实际目录占住数据库文件路径，不依赖任何盘符或权限设置。"""
        path = workdir / "directory-instead-of-database"
        path.mkdir()
        with pytest.raises(StorageConnectionError) as caught:
            Database(path)
        assert isinstance(caught.value.__cause__, sqlite3.OperationalError)
        assert path.is_dir()

    def test_connection_error_preserves_cause(self, workdir: Path) -> None:
        """父路径是普通文件时真实失败，必须映射并保留文件系统 cause。"""
        parent_file = workdir / "parent-is-file"
        parent_file.write_text("unchanged", encoding="utf-8")
        with pytest.raises(StorageConnectionError) as caught:
            Database(parent_file / "test.db")
        assert isinstance(caught.value.__cause__, OSError)
        assert parent_file.read_text(encoding="utf-8") == "unchanged"

    def test_path_type_validation(self) -> None:
        """path 不是 Path 实例 → TypeError。"""
        with pytest.raises(TypeError):
            Database("not_a_path")  # type: ignore[arg-type]

    def test_path_type_validation_int(self) -> None:
        with pytest.raises(TypeError):
            Database(12345)  # type: ignore[arg-type]

    def test_closed_database_schema_version_raises_programming_error(
        self, workdir: Path
    ) -> None:
        """close() 后访问 schema_version → ProgrammingError（不映射）。"""
        db = Database(workdir / "test.db")
        db.close()
        with pytest.raises(sqlite3.ProgrammingError):
            _ = db.schema_version

    def test_closed_database_connection_raises_programming_error(
        self, workdir: Path
    ) -> None:
        """close() 后通过 connection 执行 SQL → ProgrammingError（不映射）。"""
        db = Database(workdir / "test.db")
        db.close()
        with pytest.raises(sqlite3.ProgrammingError):
            db._connection.execute("SELECT 1")


class TestDatabaseReopen:
    """重复打开和 Schema 持久性测试。"""

    def test_reopen_preserves_schema_version(self, workdir: Path) -> None:
        db_path = workdir / "test.db"
        with Database(db_path) as db:
            assert db.schema_version == 1

        # 重新打开
        with Database(db_path) as db2:
            assert db2.schema_version == 1

    def test_reopen_preserves_tables(self, workdir: Path) -> None:
        db_path = workdir / "test.db"
        with Database(db_path) as db:
            db._connection.execute(
                "INSERT INTO conversations (id, title, model, created_at, updated_at) "
                "VALUES ('test-id', 'test', 'model', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )
            db._connection.commit()

        with Database(db_path) as db2:
            row = db2._connection.execute(
                "SELECT title FROM conversations WHERE id='test-id'"
            ).fetchone()
            assert row is not None
            assert row[0] == "test"

    def test_auto_create_parent_directory(self, workdir: Path) -> None:
        db_path = workdir / "sub" / "dir" / "test.db"
        assert not db_path.parent.exists()
        with Database(db_path) as db:
            assert db_path.exists()
            assert db.schema_version == 1


class TestDatabaseThreadConstraint:
    """线程约束测试（§7.4）。"""

    def test_check_same_thread_default_true(self, workdir: Path) -> None:
        """默认 check_same_thread=True：跨线程使用抛 ProgrammingError。"""
        db = Database(workdir / "test.db")
        errors: list[Exception] = []

        def cross_thread_use() -> None:
            try:
                db._connection.execute("SELECT 1")
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=cross_thread_use)
        t.start()
        t.join(timeout=5)
        db.close()

        assert len(errors) == 1
        assert isinstance(errors[0], sqlite3.ProgrammingError)


class TestDatabaseForeignKey:
    """外键约束验证。"""

    def test_foreign_key_enforced_on_messages(self, workdir: Path) -> None:
        """foreign_keys=ON：插入不存在的 conversation_id → IntegrityError。"""
        with Database(workdir / "test.db") as db:
            with pytest.raises(sqlite3.IntegrityError):
                db._connection.execute(
                    "INSERT INTO messages (conversation_id, role, content, created_at) "
                    "VALUES ('nonexistent-uuid', 'user', 'hello', '2026-01-01T00:00:00Z')"
                )

    def test_cascade_delete(self, workdir: Path) -> None:
        """ON DELETE CASCADE：删除会话时级联删除消息。"""
        with Database(workdir / "test.db") as db:
            db._connection.execute(
                "INSERT INTO conversations (id, title, model, created_at, updated_at) "
                "VALUES ('conv-1', 'test', 'model', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )
            db._connection.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES ('conv-1', 'user', 'hello', '2026-01-01T00:00:00Z')"
            )
            db._connection.commit()

            # 删除会话
            db._connection.execute("DELETE FROM conversations WHERE id='conv-1'")
            db._connection.commit()

            # 消息应被级联删除
            rows = db._connection.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id='conv-1'"
            ).fetchone()
            assert rows[0] == 0


# ============================================================================
# Task 5: Public API 导出测试
# ============================================================================

class TestPublicAPI:
    """公共 API 导出测试。"""

    def test_import_storage_module(self) -> None:
        """测试可以导入 emowall.storage 模块。"""
        import emowall.storage
        assert emowall.storage is not None

    def test_all_exports_correct_symbols(self) -> None:
        """测试 __all__ 包含正确的符号。"""
        import emowall.storage

        expected = {
            "Conversation",
            "ConversationRepository",
            "Database",
            "MessageRecord",
            "StorageConnectionError",
            "StorageError",
            "StorageIntegrityError",
            "StorageIOError",
            "StorageTimestampError",
        }
        actual = set(emowall.storage.__all__)
        assert actual == expected

    def test_can_import_all_symbols_directly(self) -> None:
        """测试可以从 emowall.storage 直接导入所有符号。"""
        from emowall.storage import (
            Conversation,
            ConversationRepository,
            Database,
            MessageRecord,
            StorageConnectionError,
            StorageError,
            StorageIntegrityError,
            StorageIOError,
            StorageTimestampError,
        )

        # 确保都能正常导入
        assert Conversation is not None
        assert ConversationRepository is not None
        assert Database is not None
        assert MessageRecord is not None
        assert StorageConnectionError is not None
        assert StorageError is not None
        assert StorageIntegrityError is not None
        assert StorageIOError is not None
        assert StorageTimestampError is not None

    def test_no_unauthorized_exports(self) -> None:
        """测试没有导出未经授权的符号。"""
        import emowall.storage

        # 检查没有导出内部实现
        assert not hasattr(emowall.storage, '_utcnow')
        assert not hasattr(emowall.storage, '_normalize_title')
        assert not hasattr(emowall.storage, '_CREATE_CONVERSATIONS')
        assert not hasattr(emowall.storage, '_SCHEMA_VERSION')

    def test_no_side_effects_on_import(self, workdir: Path) -> None:
        """冷解释器真实导入：拦截写盘、SQLite、网络、进程及线程启动。"""
        import json
        import subprocess
        import sys
        import textwrap

        script = textwrap.dedent(r"""
            import _thread
            import importlib
            import json
            import logging
            import os
            import sys
            import threading
            from pathlib import Path
            
            source_root = Path(sys.argv[1]).resolve()
            sys.path.insert(0, str(source_root))
            assert not any(name == "emowall" or name.startswith("emowall.") for name in sys.modules)
            effects = []
            
            
            def deny(effect):
                effects.append(effect)
                raise AssertionError("Unexpected cold-import side effect: " + effect)
            
            
            def audit(event, args):
                if event == "open":
                    mode, flags = args[1], args[2]
                    if isinstance(mode, str) and any(char in mode for char in "wax+"):
                        deny("filesystem write")
                    if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                        deny("filesystem write flags")
                if event.startswith("socket.") or event.startswith("sqlite3.connect"):
                    deny(event)
                if event in {
                    "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.chmod", "os.truncate",
                    "os.link", "os.symlink", "os.chdir", "os.putenv", "os.unsetenv", "os.system",
                    "os.fork", "os.posix_spawn", "subprocess.Popen",
                }:
                    deny(event)
            
            
            def no_thread(*args, **kwargs):
                deny("thread start")
            
            
            threading.Thread.start = no_thread
            _thread.start_new_thread = no_thread
            before_env = dict(os.environ)
            before_cwd = os.getcwd()
            root = logging.getLogger()
            before_logging = (tuple(root.handlers), tuple(root.filters), root.level, root.disabled)
            before_threads = tuple(threading.enumerate())
            sys.addaudithook(audit)
            storage = importlib.import_module("emowall.storage")
            assert Path(storage.__file__).resolve().is_relative_to(source_root)
            expected = {
                "Conversation": "emowall.storage.models",
                "MessageRecord": "emowall.storage.models",
                "Database": "emowall.storage.database",
                "ConversationRepository": "emowall.storage.repository",
                "StorageError": "emowall.storage.errors",
                "StorageConnectionError": "emowall.storage.errors",
                "StorageIntegrityError": "emowall.storage.errors",
                "StorageIOError": "emowall.storage.errors",
                "StorageTimestampError": "emowall.storage.errors",
            }
            assert len(storage.__all__) == len(expected)
            assert set(storage.__all__) == set(expected)
            for name, module in expected.items():
                assert getattr(storage, name) is getattr(importlib.import_module(module), name)
            namespace = {}
            exec("from emowall.storage import *", namespace)
            assert set(namespace) - {"__builtins__"} == set(expected)
            assert dict(os.environ) == before_env
            assert os.getcwd() == before_cwd
            assert (tuple(root.handlers), tuple(root.filters), root.level, root.disabled) == before_logging
            assert tuple(threading.enumerate()) == before_threads
            assert not any(name.startswith(("emowall.ai", "emowall.config", "emowall.emotion", "emowall.gui", "emowall.app")) for name in sys.modules)
            assert effects == []
            print(json.dumps({"effects": effects, "exports": sorted(expected), "cold": True}))
        """)
        before = tuple(workdir.iterdir())
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(Path(__file__).resolve().parents[1])],
            cwd=workdir, capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        assert result.returncode == 0, result.stderr
        observation = json.loads(result.stdout)
        assert observation["cold"] is True
        assert observation["effects"] == []
        assert len(observation["exports"]) == 9
        assert tuple(workdir.iterdir()) == before

    def test_circular_import_prevention(self) -> None:
        """测试没有循环导入。"""
        # 这个测试检查模块能够正常导入而不引发循环导入错误
        import emowall.storage
        import emowall.storage.errors
        import emowall.storage.models
        import emowall.storage.database
        import emowall.storage.repository

        # 确保各个模块都能被导入
        assert emowall.storage.errors is not None
        assert emowall.storage.models is not None
        assert emowall.storage.database is not None
        assert emowall.storage.repository is not None


# ============================================================================
# Task 4: ConversationRepository 测试
# ============================================================================

from emowall.storage.repository import ConversationRepository


class TestRepositoryConstructor:
    """Repository 构造测试。"""

    def test_valid_database(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            assert repo is not None

    def test_invalid_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            ConversationRepository("not a database")  # type: ignore[arg-type]

    def test_invalid_type_none(self) -> None:
        with pytest.raises(TypeError):
            ConversationRepository(None)  # type: ignore[arg-type]


class TestRepositoryCreate:
    """create() 测试。"""

    def test_create_normal(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="测试会话", model="qwen3:8b")

            assert isinstance(conv, Conversation)
            assert conv.title == "测试会话"
            assert conv.model == "qwen3:8b"
            assert conv.id is not None
            assert len(conv.id) == 36  # UUID v4 格式
            assert conv.created_at.endswith("Z")
            assert conv.updated_at.endswith("Z")

    def test_create_empty_title(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="", model="qwen3:8b")
            assert conv.title == "新会话"

    def test_create_whitespace_title(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="   ", model="qwen3:8b")
            assert conv.title == "新会话"

    def test_create_long_title_truncated(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="a" * 30, model="qwen3:8b")
            assert len(conv.title) == 20
            assert conv.title == "a" * 17 + "..."

    def test_create_empty_model_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(ValueError):
                repo.create(title="test", model="")

    def test_create_whitespace_model_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(ValueError):
                repo.create(title="test", model="   ")

    def test_create_strips_model_whitespace(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="  qwen3:8b  ")
            assert conv.model == "qwen3:8b"

    def test_create_id_is_uuid_v4(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            # UUID v4 格式验证
            import uuid as uuid_module
            parsed = uuid_module.UUID(conv.id)
            assert parsed.version == 4


class TestRepositoryListRecent:
    """list_recent() 测试。"""

    def test_empty_database(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            result = repo.list_recent()
            assert result == []

    def test_multiple_conversations_ordered(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv1 = repo.create(title="first", model="qwen3:8b")
            import time
            time.sleep(0.01)  # 确保时间戳不同
            conv2 = repo.create(title="second", model="qwen3:8b")

            result = repo.list_recent()
            assert len(result) == 2
            # 最新的在前
            assert result[0].id == conv2.id
            assert result[1].id == conv1.id

    def test_limit_zero_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(ValueError):
                repo.list_recent(limit=0)

    def test_limit_negative_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(ValueError):
                repo.list_recent(limit=-1)

    def test_limit_positive(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            repo.create(title="first", model="qwen3:8b")
            repo.create(title="second", model="qwen3:8b")
            repo.create(title="third", model="qwen3:8b")

            result = repo.list_recent(limit=2)
            assert len(result) == 2


class TestRepositoryGet:
    """get() 测试。"""

    def test_existing_conversation(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            created = repo.create(title="test", model="qwen3:8b")
            fetched = repo.get(created.id)

            assert fetched is not None
            assert fetched.id == created.id
            assert fetched.title == created.title

    def test_nonexistent_returns_none(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            result = repo.get("nonexistent-uuid")
            assert result is None


class TestRepositoryRename:
    """rename() 测试。"""

    def test_rename_normal(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="old", model="qwen3:8b")
            repo.rename(conv.id, "new title")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.title == "new title"

    def test_rename_empty_title(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="old", model="qwen3:8b")
            repo.rename(conv.id, "")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.title == "新会话"

    def test_rename_long_title_truncated(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="old", model="qwen3:8b")
            repo.rename(conv.id, "a" * 30)

            updated = repo.get(conv.id)
            assert updated is not None
            assert len(updated.title) == 20

    def test_rename_nonexistent_raises_integrity_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(StorageIntegrityError):
                repo.rename("nonexistent-uuid", "new title")

    def test_rename_updates_updated_at(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="old", model="qwen3:8b")
            old_updated_at = conv.updated_at

            import time
            time.sleep(0.01)
            repo.rename(conv.id, "new")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.updated_at != old_updated_at


class TestRepositoryDelete:
    """delete() 测试。"""

    def test_delete_normal(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            repo.delete(conv.id)

            result = repo.get(conv.id)
            assert result is None

    def test_delete_nonexistent_silent(self, workdir: Path) -> None:
        """delete() 幂等：不存在的会话静默删除。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            # 不应抛出异常
            repo.delete("nonexistent-uuid")

    def test_delete_cascades_messages(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            repo.append_message(conv.id, role="user", content="hello")
            repo.append_message(conv.id, role="assistant", content="hi")

            repo.delete(conv.id)

            messages = repo.list_messages(conv.id)
            assert messages == []


class TestRepositoryAppendMessage:
    """append_message() 测试。"""

    def test_append_normal(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            assert isinstance(msg, MessageRecord)
            assert msg.id is not None
            assert msg.conversation_id == conv.id
            assert msg.role == "user"
            assert msg.content == "hello"
            assert msg.emotion is None
            assert msg.emotion_intensity is None

    def test_append_invalid_role_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            with pytest.raises(ValueError):
                repo.append_message(conv.id, role="invalid", content="hello")

    def test_append_emotion_intensity_out_of_range(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            with pytest.raises(ValueError):
                repo.append_message(
                    conv.id, role="user", content="hello",
                    emotion="happy", emotion_intensity=1.5
                )

    def test_append_negative_emotion_intensity(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            with pytest.raises(ValueError):
                repo.append_message(
                    conv.id, role="user", content="hello",
                    emotion="happy", emotion_intensity=-0.1
                )

    def test_append_nonexistent_conversation_raises_integrity_error(
        self, workdir: Path
    ) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(StorageIntegrityError):
                repo.append_message("nonexistent-uuid", role="user", content="hello")

    def test_append_empty_content_allowed(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="")
            assert msg.content == ""

    def test_append_with_emotion(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(
                conv.id, role="user", content="hello",
                emotion="happy", emotion_intensity=0.8
            )
            assert msg.emotion == "happy"
            assert msg.emotion_intensity == 0.8

    def test_append_auto_title_first_user_message(self, workdir: Path) -> None:
        """第一条用户消息触发自动标题。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="initial", model="qwen3:8b")
            repo.append_message(conv.id, role="user", content="这是第一条消息")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.title == "这是第一条消息"

    def test_append_auto_title_long_content_truncated(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="initial", model="qwen3:8b")
            repo.append_message(conv.id, role="user", content="a" * 30)

            updated = repo.get(conv.id)
            assert updated is not None
            assert len(updated.title) == 20

    def test_append_auto_title_not_triggered_by_system(
        self, workdir: Path
    ) -> None:
        """system 消息不触发自动标题。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="initial", model="qwen3:8b")
            repo.append_message(conv.id, role="system", content="system message")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.title == "initial"

    def test_append_auto_title_not_triggered_by_assistant(
        self, workdir: Path
    ) -> None:
        """assistant 消息不触发自动标题。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="initial", model="qwen3:8b")
            repo.append_message(conv.id, role="assistant", content="response")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.title == "initial"

    def test_append_auto_title_only_first_user_message(
        self, workdir: Path
    ) -> None:
        """后续用户消息不改变标题。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="initial", model="qwen3:8b")
            repo.append_message(conv.id, role="user", content="first")
            repo.append_message(conv.id, role="user", content="second")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.title == "first"

    def test_append_updates_updated_at(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            old_updated_at = conv.updated_at

            import time
            time.sleep(0.01)
            repo.append_message(conv.id, role="user", content="hello")

            updated = repo.get(conv.id)
            assert updated is not None
            assert updated.updated_at != old_updated_at


class TestRepositoryListMessages:
    """list_messages() 测试。"""

    def test_empty_conversation(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            messages = repo.list_messages(conv.id)
            assert messages == []

    def test_multiple_messages_ordered(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg1 = repo.append_message(conv.id, role="user", content="first")
            msg2 = repo.append_message(conv.id, role="assistant", content="second")
            msg3 = repo.append_message(conv.id, role="user", content="third")

            messages = repo.list_messages(conv.id)
            assert len(messages) == 3
            assert messages[0].id == msg1.id
            assert messages[1].id == msg2.id
            assert messages[2].id == msg3.id

    def test_limit_zero_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            with pytest.raises(ValueError):
                repo.list_messages(conv.id, limit=0)

    def test_limit_negative_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            with pytest.raises(ValueError):
                repo.list_messages(conv.id, limit=-1)

    def test_limit_positive(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            repo.append_message(conv.id, role="user", content="first")
            repo.append_message(conv.id, role="assistant", content="second")
            repo.append_message(conv.id, role="user", content="third")

            messages = repo.list_messages(conv.id, limit=2)
            assert len(messages) == 2

    def test_limit_none_returns_all(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            for i in range(10):
                repo.append_message(conv.id, role="user", content=f"msg{i}")

            messages = repo.list_messages(conv.id, limit=None)
            assert len(messages) == 10

    def test_nonexistent_conversation_returns_empty(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            messages = repo.list_messages("nonexistent-uuid")
            assert messages == []


class TestRepositoryUpdateMessageEmotion:
    """update_message_emotion() 测试（预留接口）。"""

    def test_update_normal(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            updated = repo.update_message_emotion(
                msg.id, emotion="happy", emotion_intensity=0.8
            )

            assert updated.id == msg.id
            assert updated.emotion == "happy"
            assert updated.emotion_intensity == 0.8

    def test_update_nonexistent_message_raises_integrity_error(
        self, workdir: Path
    ) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(StorageIntegrityError):
                repo.update_message_emotion(
                    999999, emotion="happy", emotion_intensity=0.8
                )

    def test_update_empty_emotion_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            with pytest.raises(ValueError):
                repo.update_message_emotion(
                    msg.id, emotion="", emotion_intensity=0.8
                )

    def test_update_whitespace_emotion_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            with pytest.raises(ValueError):
                repo.update_message_emotion(
                    msg.id, emotion="   ", emotion_intensity=0.8
                )

    def test_update_intensity_out_of_range(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            with pytest.raises(ValueError):
                repo.update_message_emotion(
                    msg.id, emotion="happy", emotion_intensity=1.5
                )

    def test_update_message_id_zero_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(ValueError):
                repo.update_message_emotion(
                    0, emotion="happy", emotion_intensity=0.8
                )

    def test_update_message_id_negative_raises_value_error(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            with pytest.raises(ValueError):
                repo.update_message_emotion(
                    -1, emotion="happy", emotion_intensity=0.8
                )

    def test_update_persisted(self, workdir: Path) -> None:
        """更新后再次查询验证持久化。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            repo.update_message_emotion(
                msg.id, emotion="happy", emotion_intensity=0.8
            )

            messages = repo.list_messages(conv.id)
            assert len(messages) == 1
            assert messages[0].emotion == "happy"
            assert messages[0].emotion_intensity == 0.8

    def test_update_strips_emotion_whitespace(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            updated = repo.update_message_emotion(
                msg.id, emotion="  happy  ", emotion_intensity=0.8
            )
            assert updated.emotion == "happy"


# ============================================================================
# 独立审查修复回归测试（F-01 至 F-08）
# ============================================================================

import sqlite3
import threading
from unittest.mock import MagicMock, PropertyMock, patch


def _insert_conv(
    db: "Database",
    conv_id: str,
    updated_at: str,
    title: str = "t",
    model: str = "m",
) -> None:
    """直接插入一条会话（绕过 Repository，用于构造历史时间戳）。"""
    db._connection.execute(
        "INSERT INTO conversations (id, title, model, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conv_id, title, model, updated_at, updated_at),
    )
    db._connection.commit()


class _ProxyConn:
    """包装真实 sqlite3 连接，用于在运行时注入故障（F-02 / F-06）。

    ``sqlite3.Connection`` 是 C 扩展类型，无法直接 monkeypatch 其方法；
    但 ``Database._connection`` 是 Python property，可用 PropertyMock 替换为
    本代理对象，从而在真实运行路径上注入异常。
    """

    def __init__(self, real, on_execute=None, on_commit=None):
        self._real = real
        self._on_execute = on_execute
        self._on_commit = on_commit

    @property
    def in_transaction(self) -> bool:
        return self._real.in_transaction

    def execute(self, sql, params=()):
        if self._on_execute is not None:
            self._on_execute(sql, params)  # 可能抛异常
        return self._real.execute(sql, params)

    def executemany(self, sql, seq):
        return self._real.executemany(sql, seq)

    def commit(self):
        if self._on_commit is not None:
            self._on_commit()  # 可能抛异常
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()

    def close(self):
        return self._real.close()


class TestF01TransactionOwnership:
    """F-01: Repository 事务所有权测试。"""

    def test_create_rejects_external_transaction(self, workdir: Path) -> None:
        """当存在外部活动事务时，create() 应拒绝操作。"""
        with Database(workdir / "test.db") as db:
            # 手动开启一个事务
            db._connection.execute("BEGIN")
            repo = ConversationRepository(db)
            with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                repo.create(title="test", model="qwen3:8b")
            # 回滚外部事务
            db._connection.execute("ROLLBACK")

    def test_append_message_rejects_external_transaction(self, workdir: Path) -> None:
        """当存在外部活动事务时，append_message() 应拒绝操作。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            # 手动开启一个事务
            db._connection.execute("BEGIN")
            with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                repo.append_message(conv.id, role="user", content="hello")
            db._connection.execute("ROLLBACK")

    def test_rename_rejects_external_transaction(self, workdir: Path) -> None:
        """当存在外部活动事务时，rename() 应拒绝操作。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            db._connection.execute("BEGIN")
            with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                repo.rename(conv.id, "new title")
            db._connection.execute("ROLLBACK")

    def test_delete_rejects_external_transaction(self, workdir: Path) -> None:
        """当存在外部活动事务时，delete() 应拒绝操作。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            db._connection.execute("BEGIN")
            with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                repo.delete(conv.id)
            db._connection.execute("ROLLBACK")

    def test_update_emotion_rejects_external_transaction(self, workdir: Path) -> None:
        """当存在外部活动事务时，update_message_emotion() 应拒绝操作。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")
            db._connection.execute("BEGIN")
            with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                repo.update_message_emotion(msg.id, emotion="happy", emotion_intensity=0.8)
            db._connection.execute("ROLLBACK")


class TestF02EmotionUpdateAtomicity:
    """F-02: 情绪更新原子性测试。"""

    def test_update_returns_correct_record_after_commit(self, workdir: Path) -> None:
        """update_message_emotion() 返回的记录应与提交后数据库中的记录一致。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="test", model="qwen3:8b")
            msg = repo.append_message(conv.id, role="user", content="hello")

            updated = repo.update_message_emotion(
                msg.id, emotion="happy", emotion_intensity=0.8
            )

            # 验证返回的记录
            assert updated.emotion == "happy"
            assert updated.emotion_intensity == 0.8

            # 验证数据库中的记录
            messages = repo.list_messages(conv.id)
            assert len(messages) == 1
            assert messages[0].emotion == "happy"
            assert messages[0].emotion_intensity == 0.8


class TestF03MixedTimestampSorting:
    """F-03: 旧秒级 / 新毫秒级时间戳混合排序（确定性用例）。

    缺陷：纯字符串 DESC 在**同一秒**内把 ``...:00Z`` 排在 ``...:00.123Z`` 之前，
    因 ``'Z'(90) > '.'(46)``；而后者实际晚 123 ms。
    """

    def test_same_second_old_vs_new_ms(self, workdir: Path) -> None:
        """旧秒级与新毫秒级处于同一秒：新（晚 123ms）必须排在前面。"""
        with Database(workdir / "test.db") as db:
            _insert_conv(db, "old-sec", "2026-10-24T12:00:00Z")
            _insert_conv(db, "new-ms", "2026-10-24T12:00:00.123Z")
            repo = ConversationRepository(db)

            result = repo.list_recent()
            assert [c.id for c in result] == ["new-ms", "old-sec"], (
                "新记录晚 123ms，必须排在旧秒级记录之前"
            )

    def test_new_is_123ms_later_than_old(self, workdir: Path) -> None:
        """显式验证两记录相差 123ms 且排序符合真实时间序。"""
        import datetime

        old_s = "2026-10-24T12:00:00Z"
        new_s = "2026-10-24T12:00:00.123Z"
        old_dt = datetime.datetime.fromisoformat(old_s.replace("Z", "+00:00"))
        new_dt = datetime.datetime.fromisoformat(new_s.replace("Z", "+00:00"))
        assert (new_dt - old_dt).total_seconds() == 0.123

        with Database(workdir / "test.db") as db:
            _insert_conv(db, "old-sec", old_s)
            _insert_conv(db, "new-ms", new_s)
            repo = ConversationRepository(db)
            result = repo.list_recent()
            assert result[0].id == "new-ms"
            assert result[1].id == "old-sec"

    def test_multiple_millisecond_values_ordered(self, workdir: Path) -> None:
        """同一秒内多个毫秒值与秒级混合，按真实时间降序。"""
        with Database(workdir / "test.db") as db:
            _insert_conv(db, "sec", "2026-10-24T12:00:00Z")
            _insert_conv(db, "ms123", "2026-10-24T12:00:00.123Z")
            _insert_conv(db, "ms500", "2026-10-24T12:00:00.500Z")
            _insert_conv(db, "ms999", "2026-10-24T12:00:00.999Z")
            _insert_conv(db, "next-sec", "2026-10-24T12:00:01Z")
            repo = ConversationRepository(db)

            result = repo.list_recent()
            assert [c.id for c in result] == [
                "next-sec",
                "ms999",
                "ms500",
                "ms123",
                "sec",
            ]

    def test_historical_db_reopened_keeps_ordering(self, workdir: Path) -> None:
        """历史混合数据关闭后重新打开，排序仍正确。"""
        path = workdir / "hist.db"
        with Database(path) as db:
            _insert_conv(db, "old-sec", "2026-10-24T12:00:00Z")
            _insert_conv(db, "new-ms", "2026-10-24T12:00:00.123Z")

        with Database(path) as db:
            repo = ConversationRepository(db)
            result = repo.list_recent()
            assert [c.id for c in result] == ["new-ms", "old-sec"]

    def test_old_only_database_still_readable(self, workdir: Path) -> None:
        """仅含旧秒级格式的数据库仍可读取且按时间降序。"""
        path = workdir / "oldonly.db"
        with Database(path) as db:
            _insert_conv(db, "a", "2026-10-24T10:00:00Z")
            _insert_conv(db, "b", "2026-10-24T10:00:10Z")
            _insert_conv(db, "c", "2026-10-24T10:00:05Z")
            repo = ConversationRepository(db)
            assert [c.id for c in repo.list_recent()] == ["b", "c", "a"]

    def test_limit_applies_after_correct_ordering(self, workdir: Path) -> None:
        """limit 截断应发生在正确排序之后（取真正最新的 N 条）。"""
        with Database(workdir / "test.db") as db:
            _insert_conv(db, "old-sec", "2026-10-24T12:00:00Z")
            _insert_conv(db, "new-ms", "2026-10-24T12:00:00.123Z")
            _insert_conv(db, "older", "2026-10-24T11:00:00Z")
            repo = ConversationRepository(db)
            result = repo.list_recent(limit=2)
            assert [c.id for c in result] == ["new-ms", "old-sec"]

    def test_unknown_fraction_precision_falls_back_correctly(
        self, workdir: Path
    ) -> None:
        """非 0/3 位小数（如 6 位）走 strftime 兜底，仍按真实时间排序。"""
        with Database(workdir / "test.db") as db:
            _insert_conv(db, "ms001", "2026-10-24T12:00:00.001Z")
            _insert_conv(db, "us123456", "2026-10-24T12:00:00.123456Z")
            _insert_conv(db, "ms500", "2026-10-24T12:00:00.500Z")
            repo = ConversationRepository(db)
            result = repo.list_recent()
            assert [c.id for c in result] == ["ms500", "us123456", "ms001"]

    def test_identical_timestamp_tie_break_stable(self, workdir: Path) -> None:
        """归一化后并列时按 rowid DESC（后插入者在前），结果稳定。"""
        with Database(workdir / "test.db") as db:
            _insert_conv(db, "first", "2026-10-24T12:00:00Z")
            _insert_conv(db, "second", "2026-10-24T12:00:00.000Z")
            repo = ConversationRepository(db)
            assert [c.id for c in repo.list_recent()] == ["second", "first"]


class TestF04CrossThreadClose:
    """F-04: 数据库连接关闭（真实跨线程 / 状态一致性）。

    缺陷：非创建线程 ``close()`` 抛 ``ProgrammingError`` 后被吞没，
    且 ``finally`` 把 ``_closed`` 置 True，导致连接实际仍打开却标记已关闭，
    创建线程的合法关闭被错误跳过。
    """

    def test_close_in_creating_thread(self, workdir: Path) -> None:
        """创建线程正常关闭。"""
        db = Database(workdir / "test.db")
        assert db._closed is False
        db.close()
        assert db._closed is True

    def test_repeated_close_idempotent(self, workdir: Path) -> None:
        """正常关闭后重复调用 close() 保持幂等。"""
        db = Database(workdir / "test.db")
        db.close()
        db.close()
        db.close()
        assert db._closed is True

    def test_real_connection_is_closed(self, workdir: Path) -> None:
        """真实连接最终已关闭，而不只是状态变量变化。"""
        db = Database(workdir / "test.db")
        conn = db._connection
        db.close()
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_close_from_non_creating_thread_propagates(self, workdir: Path) -> None:
        """非创建线程首次关闭：ProgrammingError 必须向上传播，不能被吞没。"""
        db = Database(workdir / "test.db")
        captured: dict[str, object] = {}

        def worker() -> None:
            try:
                db.close()
                captured["result"] = "no-exception"
            except BaseException as exc:  # noqa: BLE001 - 测试需要捕获真实异常
                captured["exc"] = exc

        t = threading.Thread(target=worker)
        t.start()
        t.join(10)
        assert not t.is_alive(), "工作线程未在 10s 内结束"

        assert "exc" in captured, (
            "跨线程 close() 必须抛出 ProgrammingError，而不是被吞没"
        )
        assert isinstance(captured["exc"], sqlite3.ProgrammingError), (
            f"期望 ProgrammingError，实际 {type(captured['exc']).__name__}"
        )

    def test_closed_flag_not_set_after_cross_thread_failure(
        self, workdir: Path
    ) -> None:
        """跨线程关闭失败后，_closed 必须保持 False（状态与实际一致）。"""
        db = Database(workdir / "test.db")

        def worker() -> None:
            try:
                db.close()
            except sqlite3.ProgrammingError:
                pass

        t = threading.Thread(target=worker)
        t.start()
        t.join(10)
        assert db._closed is False, "关闭失败不得错误置 _closed=True"

    def test_connection_still_open_after_cross_thread_failure(
        self, workdir: Path
    ) -> None:
        """跨线程关闭失败后，真实连接仍然可用（未被关闭）。"""
        db = Database(workdir / "test.db")

        def worker() -> None:
            try:
                db.close()
            except sqlite3.ProgrammingError:
                pass

        t = threading.Thread(target=worker)
        t.start()
        t.join(10)

        assert db._closed is False
        assert db._connection.execute("SELECT 1").fetchone()[0] == 1

    def test_creating_thread_can_close_after_cross_thread_failure(
        self, workdir: Path
    ) -> None:
        """跨线程关闭失败后，创建线程仍能正确关闭连接。"""
        db = Database(workdir / "test.db")

        def worker() -> None:
            try:
                db.close()
            except sqlite3.ProgrammingError:
                pass

        t = threading.Thread(target=worker)
        t.start()
        t.join(10)

        assert db._closed is False
        db.close()
        assert db._closed is True
        with pytest.raises(sqlite3.ProgrammingError):
            db._connection.execute("SELECT 1")

    def test_close_from_other_thread_after_closed_is_noop(
        self, workdir: Path
    ) -> None:
        """已关闭后再从其他线程 close()：应幂等无操作（不触发跨线程错误）。"""
        db = Database(workdir / "test.db")
        db.close()

        captured: dict[str, object] = {}

        def worker() -> None:
            try:
                db.close()
                captured["result"] = "ok"
            except BaseException as exc:  # noqa: BLE001
                captured["exc"] = exc

        t = threading.Thread(target=worker)
        t.start()
        t.join(10)
        assert captured.get("result") == "ok", (
            f"已关闭后跨线程 close() 应幂等，实际 {captured}"
        )

    def test_context_manager_closes_on_normal_exit(self, workdir: Path) -> None:
        """with 正常退出时真实连接被关闭。"""
        path = workdir / "ctx.db"
        with Database(path) as db:
            conn = db._connection
            assert db._closed is False
        assert db._closed is True
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_context_manager_propagates_body_exception_and_closes(
        self, workdir: Path
    ) -> None:
        """with 体内异常向上传播，同时连接被释放。"""
        path = workdir / "ctx2.db"
        holder: dict[str, object] = {}
        with pytest.raises(RuntimeError, match="boom"):
            with Database(path) as db:
                holder["db"] = db
                holder["conn"] = db._connection
                raise RuntimeError("boom")

        db_obj = holder["db"]
        assert db_obj._closed is True  # type: ignore[attr-defined]
        with pytest.raises(sqlite3.ProgrammingError):
            holder["conn"].execute("SELECT 1")  # type: ignore[union-attr]


class TestF05PrivateConnection:
    """F-05: 私有连接封装测试。"""

    def test_connection_is_private(self) -> None:
        """Database.connection 不再是公共属性。"""
        # 验证 _connection 是私有属性
        assert hasattr(Database, '_connection')
        # 验证没有公共的 connection 属性
        assert not hasattr(Database, 'connection') or not isinstance(
            getattr(Database, 'connection', None), property
        )

    def test_repository_uses_private_connection(self, workdir: Path) -> None:
        """Repository 应通过 _connection 访问底层连接。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            # Repository 应能正常工作
            conv = repo.create(title="test", model="qwen3:8b")
            assert conv.id is not None


class TestF06RuntimeOSErrorMapping:
    """F-06: 只读查询的运行时 OSError → StorageIOError 映射（真实执行路径）。

    通过 PropertyMock 替换 ``Database._connection`` 为故障代理，
    使 ``OSError`` 在 RuntimeException 路径上真实抛出。
    """

    @staticmethod
    def _raise_enospc(sql, params=()):
        raise OSError(28, "No space left on device (injected)")

    def test_list_recent_maps_runtime_oserror(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            proxy = _ProxyConn(db._connection, on_execute=self._raise_enospc)
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIOError, match="文件系统错误") as ei:
                    repo.list_recent()
            assert isinstance(ei.value.__cause__, OSError)
            assert ei.value.__cause__.errno == 28  # type: ignore[attr-defined]

    def test_get_maps_runtime_oserror(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            proxy = _ProxyConn(db._connection, on_execute=self._raise_enospc)
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIOError, match="文件系统错误") as ei:
                    repo.get("any-id")
            assert isinstance(ei.value.__cause__, OSError)

    def test_list_messages_maps_runtime_oserror(self, workdir: Path) -> None:
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            proxy = _ProxyConn(db._connection, on_execute=self._raise_enospc)
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIOError, match="文件系统错误") as ei:
                    repo.list_messages("any-id")
            assert isinstance(ei.value.__cause__, OSError)

    def test_mapping_does_not_swallow_programming_error(self, workdir: Path) -> None:
        """ProgrammingError 不应被映射为 StorageIOError（契约 §5.2.3）。"""

        def raise_prog(sql, params=()):
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")

        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            proxy = _ProxyConn(db._connection, on_execute=raise_prog)
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(sqlite3.ProgrammingError):
                    repo.list_recent()


class TestF02RollbackOnFailure:
    """F-02: 情绪更新在 SELECT / COMMIT 失败时必须回滚，不得部分提交。"""

    @staticmethod
    def _fail_select_after_update(sql, params=()):
        s = sql.lstrip().upper()
        if s.startswith("SELECT") and "FROM MESSAGES WHERE ID" in s:
            raise sqlite3.OperationalError("disk I/O error (injected in SELECT)")

    def test_select_failure_rolls_back_update(self, workdir: Path) -> None:
        """UPDATE 后的 SELECT 失败 → 回滚，数据库中情绪保持未更新。"""
        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="t", model="m")
            msg = repo.append_message(conv.id, role="user", content="hello")
            assert msg.emotion is None

            proxy = _ProxyConn(
                db._connection, on_execute=self._fail_select_after_update
            )
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIOError, match="数据库操作失败") as ei:
                    repo.update_message_emotion(
                        msg.id, emotion="happy", emotion_intensity=0.8
                    )
            assert isinstance(ei.value.__cause__, sqlite3.OperationalError)

            # 回滚生效：无部分提交
            after = repo.list_messages(conv.id)
            assert len(after) == 1
            assert after[0].emotion is None
            assert after[0].emotion_intensity is None

    def test_commit_failure_rolls_back_update(self, workdir: Path) -> None:
        """COMMIT 失败 → 回滚，数据库中情绪保持未更新。"""

        def fail_commit():
            raise sqlite3.OperationalError("disk full (injected in COMMIT)")

        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="t", model="m")
            msg = repo.append_message(conv.id, role="user", content="hello")

            proxy = _ProxyConn(db._connection, on_commit=fail_commit)
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIOError, match="数据库操作失败"):
                    repo.update_message_emotion(
                        msg.id, emotion="happy", emotion_intensity=0.8
                    )

            after = repo.list_messages(conv.id)
            assert after[0].emotion is None

    def test_commit_failure_does_not_report_success(self, workdir: Path) -> None:
        """提交失败绝不能返回成功记录。"""

        def fail_commit():
            raise sqlite3.OperationalError("injected commit failure")

        with Database(workdir / "test.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="t", model="m")
            msg = repo.append_message(conv.id, role="user", content="hello")

            proxy = _ProxyConn(db._connection, on_commit=fail_commit)
            returned = []
            with patch.object(
                Database, "_connection", new_callable=PropertyMock
            ) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIOError):
                    returned.append(
                        repo.update_message_emotion(
                            msg.id, emotion="happy", emotion_intensity=0.8
                        )
                    )
            assert returned == [], "提交失败时不得返回 MessageRecord"


class TestF08PrivacyOptimization:
    """F-08: 隐私优化测试。"""

    def test_create_log_does_not_contain_title(self, workdir: Path, caplog: pytest.LogCaptureFixture) -> None:
        """create() 的日志不应包含会话标题。"""
        import logging
        with caplog.at_level(logging.DEBUG, logger="emowall.storage"):
            with Database(workdir / "test.db") as db:
                repo = ConversationRepository(db)
                repo.create(title="敏感标题", model="qwen3:8b")

        # 检查日志中不包含标题
        for record in caplog.records:
            assert "敏感标题" not in record.message

    def test_rename_log_does_not_contain_title(self, workdir: Path, caplog: pytest.LogCaptureFixture) -> None:
        """rename() 的日志不应包含会话标题。"""
        import logging
        with caplog.at_level(logging.DEBUG, logger="emowall.storage"):
            with Database(workdir / "test.db") as db:
                repo = ConversationRepository(db)
                conv = repo.create(title="old", model="qwen3:8b")
                caplog.clear()
                repo.rename(conv.id, "新敏感标题")

        for record in caplog.records:
            assert "新敏感标题" not in record.message

    def test_update_emotion_log_does_not_contain_emotion(self, workdir: Path, caplog: pytest.LogCaptureFixture) -> None:
        """update_message_emotion() 的日志不应包含情绪值。"""
        import logging
        with caplog.at_level(logging.DEBUG, logger="emowall.storage"):
            with Database(workdir / "test.db") as db:
                repo = ConversationRepository(db)
                conv = repo.create(title="test", model="qwen3:8b")
                msg = repo.append_message(conv.id, role="user", content="hello")
                caplog.clear()
                repo.update_message_emotion(msg.id, emotion="敏感情绪", emotion_intensity=0.8)

        for record in caplog.records:
            assert "敏感情绪" not in record.message


class TestRound4TimestampSorting:
    """固定常量、双插入顺序，防止 rowid 偶然掩盖精度损失。"""

    @pytest.mark.parametrize("newest_first", [False, True])
    @pytest.mark.parametrize(
        ("older", "newer"),
        [
            ("00Z", "00.001Z"),
            ("00Z", "00.000001Z"),
            ("00.123Z", "00.123100Z"),  # 审查案例 A
            ("00.123100Z", "00.123200Z"),  # 审查案例 B
            ("00.123100Z", "00.123101Z"),  # 相差 1 微秒
            ("00.999999Z", "01Z"),
            ("00.12Z", "00.120001Z"),
            ("00.1234Z", "00.12341Z"),
            ("00.123456788Z", "00.123456789Z"),
            ("00.1234560000000000000Z", "00.1234560000000000001Z"),
            ("00.0000000000000000000Z", "00.0000000000000000001Z"),
        ],
    )
    def test_precision_pairs(
        self, workdir: Path, older: str, newer: str, newest_first: bool
    ) -> None:
        prefix = "2026-10-24T12:00:"
        records = [("older", prefix + older), ("newer", prefix + newer)]
        if newest_first:
            records.reverse()
        with Database(workdir / "pairs.db") as db:
            for conv_id, stamp in records:
                _insert_conv(db, conv_id, stamp)
            repo = ConversationRepository(db)
            assert [c.id for c in repo.list_recent()] == ["newer", "older"]
            assert [c.id for c in repo.list_recent(limit=1)] == ["newer"]
            assert {c.id: c.updated_at for c in repo.list_recent()} == dict(records)

    @pytest.mark.parametrize("newest_first", [False, True])
    @pytest.mark.parametrize(
        "representations",
        [
            ["00Z", "00.0Z", "00.000Z", "00.000000Z"],
            ["00.123Z", "00.1230Z", "00.12300Z", "00.123000Z"],
            ["00.123456Z", "00.123456000+00:00", "00.123456000000Z", "00.1234560000000000000Z"],
        ],
    )
    def test_equal_instants_stable(
        self, workdir: Path, representations: list[str], newest_first: bool
    ) -> None:
        if newest_first:
            representations = list(reversed(representations))
        with Database(workdir / "ties.db") as db:
            for index, suffix in enumerate(representations):
                _insert_conv(db, str(index), "2026-10-24T12:00:" + suffix)
            repo = ConversationRepository(db)
            for _ in range(3):
                assert [c.id for c in repo.list_recent()] == ["3", "2", "1", "0"]
                assert [c.id for c in repo.list_recent(limit=2)] == ["3", "2"]

    def test_reopen_keeps_data_and_microsecond_order(self, workdir: Path) -> None:
        path = workdir / "historical.db"
        records = [
            ("us200", "2026-10-24T12:00:00.123200Z"),
            ("us100", "2026-10-24T12:00:00.123100Z"),
            ("ms", "2026-10-24T12:00:00.123Z"),
            ("sec", "2026-10-24T12:00:00Z"),
        ]
        with Database(path) as db:
            for conv_id, stamp in records:
                _insert_conv(db, conv_id, stamp)
            before = list(db._connection.iterdump())
        for _ in range(2):
            with Database(path) as db:
                repo = ConversationRepository(db)
                result = repo.list_recent()
                assert [(c.id, c.updated_at) for c in result] == records
                assert [(c.id, c.created_at) for c in result] == records
                assert [c.id for c in repo.list_recent(limit=2)] == ["us200", "us100"]
                assert list(db._connection.iterdump()) == before
                assert not db._connection.in_transaction

    def test_utc_offset_representation_and_equal_instant(self, workdir: Path) -> None:
        with Database(workdir / "utc-offset.db") as db:
            _insert_conv(db, "us", "2026-10-24T12:00:00.123100Z")
            _insert_conv(db, "ms-offset", "2026-10-24T12:00:00.123+00:00")
            _insert_conv(db, "equal-offset", "2026-10-24T12:00:00.123100+00:00")
            _insert_conv(db, "sec-offset", "2026-10-24T12:00:00+00:00")
            repo = ConversationRepository(db)
            assert [c.id for c in repo.list_recent()] == [
                "equal-offset", "us", "ms-offset", "sec-offset"
            ]

    @pytest.mark.parametrize(
        "invalid",
        [
            "", "not-a-time", "xxxx-10-24T12:00:00Z", "xxxx-10-24T12:00:00.123Z",
            "2026-13-24T12:00:00Z", "2026-10-24T12:00:00.12xZ",
            "2026-02-30T12:00:00Z",
        ],
    )
    def test_invalid_text_fails_entire_list_and_keeps_original(
        self, workdir: Path, invalid: str
    ) -> None:
        import emowall.storage as storage

        with Database(workdir / "invalid.db") as db:
            _insert_conv(db, "valid", "2026-10-24T12:00:00.000001Z")
            _insert_conv(db, "bad-first", invalid)
            _insert_conv(db, "bad-second", invalid)
            repo = ConversationRepository(db)
            before = list(db._connection.iterdump())
            with pytest.raises(Exception) as caught:
                repo.list_recent(limit=1)
            expected = getattr(storage, "StorageTimestampError", None)
            assert expected is not None and type(caught.value) is expected
            assert caught.value.conversation_ids == ("bad-first", "bad-second")
            assert repo.get("bad-first").updated_at == invalid
            assert repo.get("bad-second").updated_at == invalid
            assert list(db._connection.iterdump()) == before


def _round4_write(
    repo: ConversationRepository, method: str, conv_id: str, message_id: int
) -> object:
    """用有效业务参数进入五个写方法的真实执行路径。"""
    if method == "create":
        return repo.create(title="new", model="m")
    if method == "rename":
        return repo.rename(conv_id, "renamed")
    if method == "delete":
        return repo.delete(conv_id)
    if method == "append_message":
        return repo.append_message(conv_id, role="user", content="new message")
    assert method == "update_message_emotion"
    return repo.update_message_emotion(message_id, emotion="happy", emotion_intensity=0.8)


class TestRound4WriteErrors:
    """异常来自真实 Repository 执行/提交路径，检查持久化与事务状态。"""

    @pytest.mark.parametrize(
        "method", ["create", "rename", "delete", "append_message", "update_message_emotion"]
    )
    @pytest.mark.parametrize("phase", ["execute", "commit"])
    @pytest.mark.parametrize(
        ("error_type", "expected_type"),
        [
            (sqlite3.ProgrammingError, sqlite3.ProgrammingError),
            (sqlite3.InterfaceError, sqlite3.InterfaceError),
            (sqlite3.OperationalError, StorageIOError),
            (sqlite3.DatabaseError, StorageIOError),
            (OSError, StorageIOError),
        ],
    )
    def test_write_error_and_rollback(
        self, workdir: Path, method: str, phase: str,
        error_type: type[Exception], expected_type: type[Exception],
    ) -> None:
        path = workdir / "errors.db"
        with Database(path) as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="original", model="m")
            msg = repo.append_message(conv.id, role="assistant", content="original")
            assert msg.id is not None
            conn = db._connection
            before = list(conn.iterdump())
            error = error_type("injected runtime error")

            def fail() -> None:
                raise error

            def fail_execute(sql: str, params: tuple[object, ...]) -> None:
                # 确保故障发生时已有真实未提交写入，而非仅测空回滚。
                conn.execute("UPDATE conversations SET title = 'uncommitted' WHERE id = ?", (conv.id,))
                assert conn.in_transaction
                fail()

            proxy = _ProxyConn(
                conn,
                on_execute=fail_execute if phase == "execute" else None,
                on_commit=fail if phase == "commit" else None,
            )
            with patch.object(Database, "_connection", new_callable=PropertyMock) as prop:
                prop.return_value = proxy
                with pytest.raises(expected_type) as caught:
                    _round4_write(repo, method, conv.id, msg.id)
            if expected_type is StorageIOError:
                assert type(caught.value) is StorageIOError
                assert caught.value.__cause__ is error
            else:
                assert caught.value is error
            assert not conn.in_transaction
            assert list(conn.iterdump()) == before
            with Database(path) as observer:
                assert list(observer._connection.iterdump()) == before

    @pytest.mark.parametrize("method", ["rename", "delete", "append_message"])
    def test_real_unsupported_binding_propagates(
        self, workdir: Path, method: str
    ) -> None:
        with Database(workdir / "binding.db") as db:
            repo = ConversationRepository(db)
            before = list(db._connection.iterdump())
            with pytest.raises(sqlite3.ProgrammingError, match="binding"):
                _round4_write(repo, method, object(), 1)  # type: ignore[arg-type]
            assert not db._connection.in_transaction
            assert list(db._connection.iterdump()) == before

    @pytest.mark.parametrize(
        "method", ["create", "rename", "delete", "append_message", "update_message_emotion"]
    )
    @pytest.mark.parametrize("finish", ["commit", "rollback"])
    def test_external_transaction_unchanged(
        self, workdir: Path, method: str, finish: str
    ) -> None:
        path = workdir / "external.db"
        with Database(path) as db, Database(path) as observer:
            repo = ConversationRepository(db)
            conv = repo.create(title="original", model="m")
            msg = repo.append_message(conv.id, role="assistant", content="original")
            assert msg.id is not None
            conn = db._connection
            before = list(conn.iterdump())
            conn.execute("UPDATE conversations SET title = 'external' WHERE id = ?", (conv.id,))
            pending = list(conn.iterdump())
            trace: list[str] = []
            conn.set_trace_callback(trace.append)
            try:
                # 项目负责人已正式批准方案 B：事务所有权误用属于编程错误。
                with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务") as caught:
                    _round4_write(repo, method, conv.id, msg.id)
            finally:
                conn.set_trace_callback(None)
            assert type(caught.value) is sqlite3.ProgrammingError
            assert trace == []  # 不执行 SQL，也不 COMMIT / ROLLBACK。
            assert conn.in_transaction
            assert list(conn.iterdump()) == pending
            assert list(observer._connection.iterdump()) == before
            getattr(conn, finish)()
            assert not conn.in_transaction
            assert list(observer._connection.iterdump()) == (pending if finish == "commit" else before)


class TestRound4ApprovedTimestampFormat:
    """项目负责人批准新生成时间戳包含秒和完整六位微秒。"""

    @pytest.mark.parametrize("microsecond", [1, 123456, 999999])
    def test_generated_timestamps_keep_six_microsecond_digits(
        self, workdir: Path, microsecond: int
    ) -> None:
        import datetime

        fixed = datetime.datetime(2026, 10, 24, 12, 34, 56, microsecond, datetime.timezone.utc)
        expected = f"2026-10-24T12:34:56.{microsecond:06d}Z"
        with Database(workdir / "approved-format.db") as db:
            repo = ConversationRepository(db)
            with patch("emowall.storage.repository.datetime.datetime") as clock:
                clock.now.return_value = fixed
                conv = repo.create(title="test", model="m")
                msg = repo.append_message(conv.id, role="assistant", content="test")
                repo.rename(conv.id, "renamed")
            assert conv.created_at == conv.updated_at == expected
            assert msg.created_at == expected
            persisted = repo.get(conv.id)
            assert persisted is not None
            assert persisted.created_at == persisted.updated_at == expected
            assert repo.list_messages(conv.id)[0].created_at == expected


# ============================================================================
# Lead Architect V2 授权的定向缺陷回归（不代表 Task 6 阶段验收）
# ============================================================================

from collections.abc import Callable


class _RollbackFailureConn(_ProxyConn):
    """保留真实未提交事务，仅使清理动作失败。"""

    def __init__(
        self, real: sqlite3.Connection, on_commit: Callable[[], None] | None = None
    ) -> None:
        super().__init__(real, on_commit=on_commit)
        self.rollback_calls = 0
        self.close_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1
        raise OSError("sensitive-cleanup-error")

    def close(self) -> None:
        self.close_calls += 1
        super().close()


class TestDirectedStorageFix:
    """真实事务状态、原异常对象和可恢复性优先于 mock 调用次数。"""

    def test_rename_missing_recovers_without_manual_rollback(self, workdir: Path) -> None:
        path = workdir / "missing-rename.db"
        with Database(path) as db:
            repo = ConversationRepository(db)
            original = repo.create(title="original", model="m")
            conn = db._connection
            before = list(conn.iterdump())
            with pytest.raises(StorageIntegrityError):
                repo.rename("missing-conversation", "renamed")
            assert not conn.in_transaction
            assert list(conn.iterdump()) == before
            created = repo.create(title="next write", model="m")
            assert repo.get(original.id) == original
            assert repo.get(created.id) == created
        with Database(path) as reopened:
            assert ConversationRepository(reopened).get(created.id) == created

    @pytest.mark.parametrize(
        "method", ["create", "rename", "delete", "append_message", "update_message_emotion"]
    )
    @pytest.mark.parametrize(
        ("error_type", "expected_type"),
        [
            (sqlite3.ProgrammingError, sqlite3.ProgrammingError),
            (sqlite3.InterfaceError, sqlite3.InterfaceError),
            (sqlite3.OperationalError, StorageIOError),
            (sqlite3.IntegrityError, StorageIntegrityError),
            (sqlite3.DatabaseError, StorageIOError),
            (OSError, StorageIOError),
        ],
    )
    def test_rollback_failure_preserves_primary_error_and_pending_state(
        self, workdir: Path, method: str, error_type: type[Exception],
        expected_type: type[Exception], caplog: pytest.LogCaptureFixture,
    ) -> None:
        path = workdir / "rollback-failure.db"
        with Database(path) as db, Database(path) as observer:
            repo = ConversationRepository(db)
            conv = repo.create(title="original", model="m")
            message = repo.append_message(conv.id, role="assistant", content="original")
            assert message.id is not None
            conn, observer_conn = db._connection, observer._connection
            before = list(conn.iterdump())
            primary = error_type("sensitive-source-error")

            def fail_commit() -> None:
                assert conn.in_transaction
                raise primary

            proxy = _RollbackFailureConn(conn, on_commit=fail_commit)
            with patch.object(Database, "_connection", new_callable=PropertyMock) as prop:
                prop.return_value = proxy
                with pytest.raises(expected_type) as caught:
                    _round4_write(repo, method, conv.id, message.id)
                if expected_type in (StorageIOError, StorageIntegrityError):
                    assert type(caught.value) is expected_type
                    assert caught.value.__cause__ is primary
                else:
                    assert caught.value is primary
                notes = " ".join(getattr(primary, "__notes__", ()))
                assert "OSError" in notes
                assert "sensitive" not in notes + caplog.text
                assert proxy.rollback_calls == 1
                assert proxy.close_calls == 0
                assert conn.in_transaction
                pending = list(conn.iterdump())
                assert pending != before
                assert list(observer_conn.iterdump()) == before

                # 清理失败未宣称恢复：现有 F-01 必须拒绝下次写入，不能顺带提交。
                trace: list[str] = []
                conn.set_trace_callback(trace.append)
                try:
                    with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                        repo.create(title="must remain blocked", model="m")
                finally:
                    conn.set_trace_callback(None)
                assert trace == []
                assert conn.in_transaction
                assert list(conn.iterdump()) == pending
                assert proxy.rollback_calls == 1
                assert proxy.close_calls == 0
                assert list(observer_conn.iterdump()) == before

    @pytest.mark.parametrize("method", ["rename", "update_message_emotion"])
    def test_business_failure_survives_rollback_failure(
        self, workdir: Path, method: str, caplog: pytest.LogCaptureFixture,
    ) -> None:
        path = workdir / "missing-and-rollback-failure.db"
        with Database(path) as db, Database(path) as observer:
            repo = ConversationRepository(db)
            conn, observer_conn = db._connection, observer._connection
            before = list(conn.iterdump())
            proxy = _RollbackFailureConn(conn)
            with patch.object(Database, "_connection", new_callable=PropertyMock) as prop:
                prop.return_value = proxy
                with pytest.raises(StorageIntegrityError) as caught:
                    if method == "rename":
                        repo.rename("missing-conversation", "new title")
                    else:
                        repo.update_message_emotion(999, emotion="happy", emotion_intensity=0.5)
                assert type(caught.value) is StorageIntegrityError
                assert caught.value.__cause__ is None
                notes = " ".join(getattr(caught.value, "__notes__", ()))
                assert "OSError" in notes
                assert "sensitive" not in notes + caplog.text
                assert proxy.rollback_calls == 1
                assert proxy.close_calls == 0
                assert conn.in_transaction
                assert list(observer_conn.iterdump()) == before
                with pytest.raises(sqlite3.ProgrammingError, match="外部活动事务"):
                    repo.create(title="must remain blocked", model="m")
                assert proxy.rollback_calls == 1

    def test_delete_real_integrity_error_is_classified_and_recovers(self, workdir: Path) -> None:
        with Database(workdir / "delete-integrity.db") as db:
            repo = ConversationRepository(db)
            conv = repo.create(title="protected", model="m")
            conn = db._connection
            conn.execute(
                "CREATE TRIGGER block_conversation_delete BEFORE DELETE ON conversations "
                "BEGIN SELECT RAISE(ABORT, 'blocked by constraint'); END"
            )
            conn.commit()
            before = list(conn.iterdump())
            with pytest.raises(StorageIntegrityError) as caught:
                repo.delete(conv.id)
            assert type(caught.value) is StorageIntegrityError
            assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)
            assert not conn.in_transaction
            assert list(conn.iterdump()) == before
            assert repo.get(conv.id) == conv
            created = repo.create(title="next write", model="m")
            assert repo.get(created.id) == created


class TestIndependentConnectionInterleaving:
    """两个真实线程各自创建、使用和关闭连接，队列明确交替，无 sleep。"""

    def test_two_threads_see_each_others_committed_changes(self, workdir: Path) -> None:
        from queue import Queue

        path = workdir / "independent-connections.db"
        to_first: Queue[object] = Queue()
        to_second: Queue[object] = Queue()
        lifecycle: Queue[tuple[str, int, int]] = Queue()
        errors: Queue[Exception] = Queue()

        def verify_closed(conn: sqlite3.Connection) -> None:
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")
            lifecycle.put(("closed", threading.get_ident(), id(conn)))

        def first() -> None:
            try:
                with Database(path) as db:
                    conn = db._connection
                    lifecycle.put(("open", threading.get_ident(), id(conn)))
                    repo = ConversationRepository(db)
                    conv = repo.create(title="first", model="m")
                    to_second.put(conv)
                    assert to_first.get(timeout=5) == "renamed"
                    renamed = repo.get(conv.id)
                    assert renamed is not None and renamed.title == "second renamed"
                    message = repo.append_message(conv.id, role="assistant", content="shared")
                    assert message.id is not None
                    to_second.put(message)
                    assert to_first.get(timeout=5) == "emotion updated"
                    messages = repo.list_messages(conv.id)
                    assert len(messages) == 1
                    assert messages[0].emotion == "happy"
                    assert messages[0].emotion_intensity == 0.8
                    assert not conn.in_transaction
                    to_second.put("verified")
                    assert to_first.get(timeout=5) == "deleted"
                    assert repo.get(conv.id) is None
                    assert repo.list_messages(conv.id) == []
                verify_closed(conn)
            except Exception as exc:
                errors.put(exc)

        def second() -> None:
            try:
                conv = to_second.get(timeout=5)
                assert isinstance(conv, Conversation)
                with Database(path) as db:
                    conn = db._connection
                    lifecycle.put(("open", threading.get_ident(), id(conn)))
                    repo = ConversationRepository(db)
                    assert repo.get(conv.id) == conv
                    repo.rename(conv.id, "second renamed")
                    to_first.put("renamed")
                    message = to_second.get(timeout=5)
                    assert isinstance(message, MessageRecord) and message.id is not None
                    assert repo.list_messages(conv.id) == [message]
                    repo.update_message_emotion(message.id, emotion="happy", emotion_intensity=0.8)
                    assert not conn.in_transaction
                    to_first.put("emotion updated")
                    assert to_second.get(timeout=5) == "verified"
                    repo.delete(conv.id)
                    to_first.put("deleted")
                verify_closed(conn)
            except Exception as exc:
                errors.put(exc)

        workers = [threading.Thread(target=first, daemon=True), threading.Thread(target=second, daemon=True)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
        assert not any(worker.is_alive() for worker in workers)
        if not errors.empty():
            raise errors.get_nowait()
        records = [lifecycle.get_nowait() for _ in range(lifecycle.qsize())]
        opened = {(thread_id, conn_id) for state, thread_id, conn_id in records if state == "open"}
        closed = {(thread_id, conn_id) for state, thread_id, conn_id in records if state == "closed"}
        assert len(opened) == 2
        assert len({thread_id for thread_id, _ in opened}) == 2
        assert len({conn_id for _, conn_id in opened}) == 2
        assert opened == closed
