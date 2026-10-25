"""Versioned v1.3 timestamp acceptance on real isolated SQLite databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import emowall.storage as storage
from emowall.storage import ConversationRepository, Database


def _insert(db: Database, conv_id: str, stamp: str, *, created_at: str | None = None) -> None:
    db._connection.execute(
        "INSERT INTO conversations (id, title, model, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conv_id, "secret-title", "m", stamp if created_at is None else created_at, stamp),
    )
    db._connection.commit()


def _timestamp_error(repo: ConversationRepository, limit: int = 50) -> Exception:
    with pytest.raises(Exception) as caught:
        repo.list_recent(limit=limit)
    expected = getattr(storage, "StorageTimestampError", None)
    assert expected is not None, "v1.3 timestamp error must be public"
    assert type(caught.value) is expected
    return caught.value


FORMS = [
    ("2026-10-24", "12:00:00"),
    ("20261024", "120000"),
    ("2026-W43-6", "12:00:00"),
    ("2026W436", "120000"),
    ("2026-297", "12:00:00"),
    ("2026297", "120000"),
]


@pytest.mark.parametrize("date,time", FORMS)
@pytest.mark.parametrize("suffix", ["Z", "+00:00", "+0000", "+00"])
@pytest.mark.parametrize("decimal", [".", ","])
def test_full_profile_combinations_are_the_same_instant(
    workdir: Path, date: str, time: str, suffix: str, decimal: str
) -> None:
    historical = f"{date}T{time}{decimal}123200{suffix}"
    canonical = "2026-10-24T12:00:00.1232Z"
    with Database(workdir / "profile.db") as db:
        # Historical value comes last, so NULL-last sorting cannot pass by rowid accident.
        _insert(db, "canonical", canonical)
        _insert(db, "historical", historical)
        repo = ConversationRepository(db)
        assert [(row.id, row.updated_at) for row in repo.list_recent()] == [
            ("historical", historical), ("canonical", canonical)
        ]
        assert [row.id for row in repo.list_recent(limit=1)] == ["historical"]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("alternative", [
    "20261024T120000.123200Z",
    "2026-10-24T12:00:00,123200Z",
    "2026-10-24T12:00:00.123200+0000",
    "2026-W43-6T12:00:00.123200Z",
    "2026-297T12:00:00.123200Z",
])
def test_historical_representations_sort_by_instant_in_both_insert_orders(
    workdir: Path, alternative: str, reverse: bool
) -> None:
    rows = [
        ("old", "2026-10-24T12:00:00.123100Z"),
        ("new", alternative),
    ]
    if reverse:
        rows.reverse()
    with Database(workdir / "ordering.db") as db:
        for conv_id, stamp in rows:
            _insert(db, conv_id, stamp)
        repo = ConversationRepository(db)
        assert [row.id for row in repo.list_recent()] == ["new", "old"]
        assert [row.id for row in repo.list_recent(limit=1)] == ["new"]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("first,second", [
    ("2020-W53-7T00:00:00Z", "2021-01-03T00:00:00.000Z"),
    ("2026-10-24T24:00:00.000Z", "2026-10-25T00:00:00Z"),
    ("2020-12-31T24:00:00,000Z", "20210101T000000+00"),
    ("2026-10-24T12:00:00.123456Z", "20261024T120000,123456000+0000"),
])
def test_equivalent_instants_use_rowid_tie_break(
    workdir: Path, reverse: bool, first: str, second: str
) -> None:
    rows = [("first", first), ("second", second)]
    if reverse:
        rows.reverse()
    with Database(workdir / "same-instant.db") as db:
        for conv_id, stamp in rows:
            _insert(db, conv_id, stamp)
        repo = ConversationRepository(db)
        assert [row.id for row in repo.list_recent()] == [rows[-1][0], rows[0][0]]
        assert repo.list_recent(limit=1)[0].id == rows[-1][0]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("older,newer", [
    ("2026-10-24T12:00:00.123456788Z", "2026-10-24T12:00:00.123456789Z"),
    ("2026-10-24T12:00:00.123456Z", "2026-10-24T12:00:00.1234560000000000001Z"),
    ("2026-10-24T12:00:00Z", "2026-10-24T12:00:00.0000000000000000001Z"),
])
def test_no_fractional_truncation(workdir: Path, older: str, newer: str, reverse: bool) -> None:
    rows = [("old", older), ("new", newer)]
    if reverse:
        rows.reverse()
    with Database(workdir / "precision.db") as db:
        for conv_id, stamp in rows:
            _insert(db, conv_id, stamp)
        repo = ConversationRepository(db)
        assert [row.id for row in repo.list_recent()] == ["new", "old"]


BAD_TIMESTAMPS = [
    "", "not-a-time", "2026-02-30T12:00:00Z", "2021-W53-1T00:00:00Z",
    "2021-366T00:00:00Z", "2026-W00-1T12:00:00Z", "2026-W43-8T12:00:00Z",
    "9999-W52-7T00:00:00Z", "9999-12-31T24:00:00Z",
    "2026-10-24T24:00:00.0000000000000000001Z",
    "2016-12-31T23:59:60Z", "2026-10-24T12:00:00+08:00",
    "2026-10-24T12:00:00-00:00", "2026-10-24T12:00:00z",
    "2026-10-24T120000Z", "20261024T12:00:00Z",
    "2026-10-24T12:00:00.Z", " 2026-10-24T12:00:00Z",
    "2026-10-24T12:00:00Z ", "2026-10-24T12:00:00Zextra",
    "2026-10-24T25:00:00Z", "2026-10-24T12:60:00Z",
    "2026-10-24T12:00:61Z", "0000-01-01T00:00:00Z",
]


@pytest.mark.parametrize("time,category,has_cause", [
    ("25:99:60", "无效", True),
    ("24:01:60", "无效", True),
    ("24:00:60", "无效", True),
    ("12:59:61", "无效", True),
    ("23:59:60", "不支持或无法识别", False),
])
def test_mixed_time_fields_report_invalid_before_leap_second_boundary(
    workdir: Path, time: str, category: str, has_cause: bool
) -> None:
    stamp = f"2026-10-24T{time}Z"
    with Database(workdir / "mixed-time-fields.db") as db:
        _insert(db, "bad", stamp)
        repo = ConversationRepository(db)
        exc = _timestamp_error(repo, limit=1)
        assert exc.conversation_ids == ("bad",)
        assert category in str(exc)
        if category == "无效":
            assert "不支持" not in str(exc)
        assert isinstance(exc.__cause__, ValueError) if has_cause else exc.__cause__ is None
        assert repo.get("bad").updated_at == stamp
        assert not db._connection.in_transaction


@pytest.mark.parametrize("invalid", BAD_TIMESTAMPS)
def test_uncomparable_row_fails_entire_list_even_outside_limit(
    workdir: Path, invalid: str
) -> None:
    with Database(workdir / "invalid.db") as db:
        _insert(db, "old-bad", invalid)
        _insert(db, "new-valid", "2026-10-25T00:00:00Z")
        repo = ConversationRepository(db)
        before = list(db._connection.iterdump())
        exc = _timestamp_error(repo, limit=1)
        assert exc.conversation_ids == ("old-bad",)
        assert not db._connection.in_transaction
        assert list(db._connection.iterdump()) == before
        assert repo.get("old-bad").updated_at == invalid
        assert repo.list_messages("old-bad") == []


def test_public_exception_is_read_only_and_diagnostics_are_safe(
    workdir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with Database(workdir / "diagnostic.db") as db:
        _insert(db, "z-bad", "not-a-time")
        _insert(db, "valid", "2026-10-24T00:00:00Z", created_at="not-a-created-time")
        _insert(db, "a-bad", "2026-02-30T00:00:00Z")
        db._connection.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("a-bad", "user", "secret-message", "not-a-message-time"),
        )
        db._connection.commit()
        repo = ConversationRepository(db)
        with caplog.at_level("DEBUG", logger="emowall.storage"):
            exc = _timestamp_error(repo, limit=1)
        assert isinstance(exc, storage.StorageError)
        assert exc.conversation_ids == ("a-bad", "z-bad")
        assert isinstance(exc.conversation_ids, tuple)
        with pytest.raises(AttributeError):
            exc.conversation_ids = ("changed",)
        combined = str(exc) + "\n" + caplog.text
        for secret in ("secret-title", "secret-message", "not-a-time", "2026-02-30"):
            assert secret not in combined
        assert repo.get("a-bad").updated_at == "2026-02-30T00:00:00Z"
        assert repo.list_messages("a-bad")[0].content == "secret-message"
        # created_at and message timestamps are outside list_recent's validation scope.
        db._connection.execute("DELETE FROM conversations WHERE id IN (?, ?)", ("a-bad", "z-bad"))
        db._connection.commit()
        assert repo.list_recent()[0].created_at == "not-a-created-time"


def test_public_export_and_old_eight_remain_identical() -> None:
    from emowall.storage.errors import StorageTimestampError
    assert storage.StorageTimestampError is StorageTimestampError
    assert issubclass(StorageTimestampError, storage.StorageError)
    assert set(storage.__all__) == {
        "Conversation", "ConversationRepository", "Database", "MessageRecord",
        "StorageConnectionError", "StorageError", "StorageIntegrityError",
        "StorageIOError", "StorageTimestampError",
    }
    assert len(storage.__all__) == 9
    namespace: dict[str, object] = {}
    exec("from emowall.storage import *", namespace)
    assert set(namespace) - {"__builtins__"} == set(storage.__all__)
    assert namespace["StorageTimestampError"] is storage.StorageTimestampError


def test_argument_error_precedes_timestamp_validation(workdir: Path) -> None:
    with Database(workdir / "args.db") as db:
        _insert(db, "bad", "not-a-time")
        repo = ConversationRepository(db)
        with pytest.raises(ValueError):
            repo.list_recent(limit=0)
        assert not db._connection.in_transaction


def test_external_transaction_survives_timestamp_failure(workdir: Path) -> None:
    with Database(workdir / "caller-transaction.db") as db:
        _insert(db, "bad", "not-a-time")
        repo = ConversationRepository(db)
        db._connection.execute("BEGIN")
        assert db._connection.in_transaction
        exc = _timestamp_error(repo)
        assert exc.conversation_ids == ("bad",)
        assert db._connection.in_transaction
        assert repo.get("bad").updated_at == "not-a-time"
        db._connection.rollback()
        assert not db._connection.in_transaction


def test_isolated_backup_export_and_authorized_repair(workdir: Path) -> None:
    original = workdir / "original.db"
    backup = workdir / "backup.db"
    with Database(original) as db:
        _insert(db, "bad", "not-a-time")
        _insert(db, "valid", "2026-10-24T12:00:00Z")
        db._connection.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("bad", "user", "historical-message", "unknown-message-time"),
        )
        db._connection.commit()
        repo = ConversationRepository(db)
        exc = _timestamp_error(repo)
        assert exc.conversation_ids == ("bad",)
        exported = (repo.get("bad"), repo.list_messages("bad"))
        assert exported[0].updated_at == "not-a-time"
        assert exported[1][0].content == "historical-message"
        destination = sqlite3.connect(backup)
        try:
            db._connection.backup(destination)
        finally:
            destination.close()
        assert original.exists() and backup.exists()
        with Database(backup) as copy_db:
            copy_repo = ConversationRepository(copy_db)
            _timestamp_error(copy_repo)
            # Only the copy receives a simulated, explicitly approved known UTC correction.
            correction_approved = True
            confirmed_utc = "2026-10-24T11:00:00.000000Z"
            assert correction_approved and confirmed_utc
            copy_db._connection.execute("BEGIN IMMEDIATE")
            copy_db._connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (confirmed_utc, "bad"),
            )
            copy_db._connection.commit()
            assert [row.id for row in copy_repo.list_recent()] == ["valid", "bad"]
            assert copy_repo.get("bad").updated_at == confirmed_utc
            assert copy_repo.list_messages("bad")[0].content == "historical-message"
        # The original still fails, retaining every raw value and message.
        _timestamp_error(repo)
        assert repo.get("bad").updated_at == "not-a-time"
        assert repo.list_messages("bad")[0].content == "historical-message"
