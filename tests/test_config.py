"""配置系统测试（Stage 1）。

覆盖：默认值、首次生成、保存/重载一致、缺失与损坏恢复、非法值回退、
未知字段保留、版本兼容、原子写入、EMOWALL_HOME 隔离。

全部离线运行：不访问网络、不依赖 Qt、不读写真实用户目录。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from emowall.config import (
    CURRENT_CONFIG_VERSION,
    AppSettings,
    ChatSettings,
    ConfigIOError,
    ConfigStore,
    ConfigValidationError,
    OllamaSettings,
    config_path,
    default_app_data_dir,
)


@pytest.fixture()
def store(workdir: Path) -> ConfigStore:
    return ConfigStore(workdir / "config.json")


def _write_config(store: ConfigStore, payload: object) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_config(store: ConfigStore) -> dict:
    return json.loads(store.path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 默认值与路径
# ---------------------------------------------------------------------------


def test_defaults_are_sane() -> None:
    settings = AppSettings()
    assert settings.ollama.base_url == "http://127.0.0.1:11434"
    assert settings.ollama.model == "qwen3:8b"
    assert 0.0 <= settings.ollama.temperature <= 2.0
    assert settings.ollama.num_ctx >= 1024
    assert settings.chat.max_context_messages >= 1
    assert settings.chat.system_prompt


def test_app_data_dir_prefers_emowall_home(monkeypatch: pytest.MonkeyPatch, workdir: Path) -> None:
    home = workdir / "custom-home"
    monkeypatch.setenv("EMOWALL_HOME", str(home))
    assert default_app_data_dir() == home
    assert config_path() == home / "config.json"


def test_app_data_dir_uses_appdata(monkeypatch: pytest.MonkeyPatch, workdir: Path) -> None:
    monkeypatch.delenv("EMOWALL_HOME", raising=False)
    appdata = workdir / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    assert default_app_data_dir() == appdata / "EmoWall"


def test_app_data_dir_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch, workdir: Path
) -> None:
    monkeypatch.delenv("EMOWALL_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: workdir))
    assert default_app_data_dir() == workdir / ".emowall"


# ---------------------------------------------------------------------------
# 首次生成与 round-trip
# ---------------------------------------------------------------------------


def test_first_load_creates_file_with_defaults(store: ConfigStore) -> None:
    settings = store.load()
    assert store.path.exists()
    raw = _read_config(store)
    assert raw["version"] == CURRENT_CONFIG_VERSION
    assert raw["ollama"]["model"] == settings.ollama.model
    assert raw["chat"]["system_prompt"] == settings.chat.system_prompt


def test_round_trip_persists_settings(store: ConfigStore) -> None:
    original = AppSettings(
        ollama=OllamaSettings(
            base_url="http://127.0.0.1:11500",
            model="llama3.1:8b",
            temperature=0.3,
            num_ctx=4096,
        ),
        chat=ChatSettings(
            max_context_messages=10,
            max_context_chars=4000,
            system_prompt="保持简短。",
        ),
    )
    store.save(original)
    assert ConfigStore(store.path).load() == original


def test_loading_twice_is_stable(store: ConfigStore) -> None:
    first = store.load()
    second = ConfigStore(store.path).load()
    assert first == second


def test_delete_file_returns_defaults(store: ConfigStore) -> None:
    store.save(AppSettings(ollama=OllamaSettings(model="custom:1b")))
    store.path.unlink()
    assert store.load() == AppSettings()
    assert store.path.exists(), "缺失时应重新生成默认配置"


# ---------------------------------------------------------------------------
# 损坏与非法配置的恢复
# ---------------------------------------------------------------------------


def test_corrupt_json_is_backed_up_and_recovers(store: ConfigStore, caplog: pytest.LogCaptureFixture) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{ 这不是 JSON", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()

    assert settings == AppSettings()
    backups = list(store.path.parent.glob("config.corrupt-*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{ 这不是 JSON"
    assert "corrupt" in caplog.text.lower()
    assert _read_config(store)["version"] == CURRENT_CONFIG_VERSION


def test_json_array_is_treated_as_corrupt(store: ConfigStore) -> None:
    _write_config(store, [1, 2, 3])
    assert store.load() == AppSettings()
    assert list(store.path.parent.glob("config.corrupt-*.json"))


def test_utf8_bom_config_is_readable(store: ConfigStore) -> None:
    """Windows 记事本保存的 UTF-8 BOM 不应被当成损坏。"""
    payload = {"version": CURRENT_CONFIG_VERSION, "ollama": {"model": "qwen3:4b"}}
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))

    settings = store.load()

    assert settings.ollama.model == "qwen3:4b"
    assert not list(store.path.parent.glob("config.corrupt-*.json"))


def test_invalid_utf8_bytes_are_treated_as_corrupt(store: ConfigStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_bytes(b'{"ollama": {"model": "\xff\xfe"}}')
    assert store.load() == AppSettings()
    assert list(store.path.parent.glob("config.corrupt-*.json"))


def test_recursion_during_parse_is_treated_as_corrupt(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{}", encoding="utf-8")

    def _explode(*args: object, **kwargs: object) -> object:
        raise RecursionError("JSON 嵌套过深")

    monkeypatch.setattr("emowall.config.store.json.loads", _explode)
    assert store.load() == AppSettings()
    assert list(store.path.parent.glob("config.corrupt-*.json"))


def test_partial_file_fills_defaults(store: ConfigStore) -> None:
    _write_config(store, {"ollama": {"model": "qwen3:4b"}})
    settings = store.load()
    assert settings.ollama.model == "qwen3:4b"
    assert settings.ollama.base_url == AppSettings().ollama.base_url
    assert settings.chat == ChatSettings()


def test_invalid_value_falls_back_per_field(store: ConfigStore, caplog: pytest.LogCaptureFixture) -> None:
    _write_config(
        store,
        {"version": CURRENT_CONFIG_VERSION, "ollama": {"temperature": 9, "model": "qwen3:4b"}},
    )
    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()

    assert settings.ollama.model == "qwen3:4b"
    assert settings.ollama.temperature == AppSettings().ollama.temperature
    assert "temperature" in caplog.text
    # 非法值不回写：保留用户文件，等用户自己修
    assert _read_config(store)["ollama"]["temperature"] == 9


def test_wrong_type_falls_back_per_field(store: ConfigStore, caplog: pytest.LogCaptureFixture) -> None:
    _write_config(store, {"version": CURRENT_CONFIG_VERSION, "ollama": {"num_ctx": "8192"}})
    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()

    assert settings.ollama.num_ctx == AppSettings().ollama.num_ctx
    assert "num_ctx" in caplog.text


def test_corrupt_backup_does_not_overwrite_when_backup_fails(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """备份失败时不得覆盖用户文件（宁可用默认值，也不破坏原文件）。"""
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{bad json", encoding="utf-8")

    def _fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("backup denied")

    monkeypatch.setattr("emowall.config.store.os.replace", _fail_replace)
    assert store.load() == AppSettings()
    assert store.path.read_text(encoding="utf-8") == "{bad json"


# ---------------------------------------------------------------------------
# 未知字段与版本兼容
# ---------------------------------------------------------------------------


def test_unknown_fields_are_preserved_on_save(store: ConfigStore) -> None:
    payload = {
        "version": CURRENT_CONFIG_VERSION,
        "ollama": {"model": "qwen3:4b", "future_flag": True},
        "chat": {"future_section": {"a": 1}},
        "experimental": {"x": 1},
    }
    _write_config(store, payload)
    store.load()
    store.save(AppSettings())

    raw = _read_config(store)
    assert raw["ollama"]["future_flag"] is True
    assert raw["chat"]["future_section"] == {"a": 1}
    assert raw["experimental"] == {"x": 1}
    assert raw["ollama"]["model"] == AppSettings().ollama.model


def test_save_without_load_preserves_existing_unknowns(store: ConfigStore) -> None:
    _write_config(store, {"version": 1, "experimental": {"x": 1}, "ollama": {"model": "m"}})
    fresh = ConfigStore(store.path)
    fresh.save(AppSettings())
    assert _read_config(store)["experimental"] == {"x": 1}


def test_newer_version_reads_known_fields(store: ConfigStore, caplog: pytest.LogCaptureFixture) -> None:
    _write_config(store, {"version": 99, "ollama": {"model": "future-model"}})
    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()
    assert settings.ollama.model == "future-model"
    assert "99" in caplog.text


def test_missing_version_is_tolerated(store: ConfigStore, caplog: pytest.LogCaptureFixture) -> None:
    _write_config(store, {"ollama": {"model": "qwen3:4b"}})
    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()
    assert settings.ollama.model == "qwen3:4b"
    assert "version" in caplog.text


def test_older_version_is_tolerated(store: ConfigStore, caplog: pytest.LogCaptureFixture) -> None:
    _write_config(store, {"version": 0, "ollama": {"model": "qwen3:4b"}})
    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()
    assert settings.ollama.model == "qwen3:4b"
    assert "0" in caplog.text


# ---------------------------------------------------------------------------
# 原子写入与安全
# ---------------------------------------------------------------------------


def test_save_leaves_no_temp_files(store: ConfigStore) -> None:
    store.save(AppSettings())
    assert list(store.path.parent.glob("config.json.*.tmp")) == []
    _read_config(store)


def test_save_creates_parent_directories(workdir: Path) -> None:
    deep = ConfigStore(workdir / "a" / "b" / "config.json")
    deep.save(AppSettings())
    assert deep.path.exists()


def test_unicode_round_trip(store: ConfigStore) -> None:
    prompt = "你好，EmoWall 🌙 —— 简洁一点。"
    store.save(AppSettings(chat=ChatSettings(system_prompt=prompt)))
    assert ConfigStore(store.path).load().chat.system_prompt == prompt


def test_emowall_home_isolates_storage(monkeypatch: pytest.MonkeyPatch, workdir: Path) -> None:
    home = workdir / "appdata"
    monkeypatch.setenv("EMOWALL_HOME", str(home))
    store = ConfigStore()
    store.save(AppSettings())
    assert store.path == home / "config.json"
    assert (home / "config.json").exists()


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [
        lambda: OllamaSettings(base_url=""),
        lambda: OllamaSettings(base_url="ftp://127.0.0.1:11434"),
        lambda: OllamaSettings(base_url="http://127.0.0.1:11434/ path"),
        lambda: OllamaSettings(model=""),
        lambda: OllamaSettings(model="   "),
        lambda: OllamaSettings(temperature=9),
        lambda: OllamaSettings(temperature=-0.1),
        lambda: OllamaSettings(num_ctx=100),
        lambda: OllamaSettings(connect_timeout_seconds=0),
        lambda: OllamaSettings(read_timeout_seconds=-1),
        lambda: ChatSettings(max_context_messages=0),
        lambda: ChatSettings(max_context_chars=10),
    ],
    ids=[
        "empty_url",
        "non_http_url",
        "url_with_space",
        "empty_model",
        "blank_model",
        "temperature_too_high",
        "temperature_negative",
        "num_ctx_too_small",
        "connect_timeout_zero",
        "read_timeout_negative",
        "no_context_messages",
        "context_chars_too_small",
    ],
)
def test_invalid_settings_are_rejected(build: object) -> None:
    with pytest.raises(ConfigValidationError):
        build()


def test_app_settings_requires_correct_types() -> None:
    with pytest.raises(ConfigValidationError):
        AppSettings(ollama="not-settings")  # type: ignore[arg-type]


def test_normalization_strips_base_url_and_model() -> None:
    settings = OllamaSettings(base_url="  http://127.0.0.1:11434  ", model=" qwen3:8b ")
    assert settings.base_url == "http://127.0.0.1:11434"
    assert settings.model == "qwen3:8b"


def test_load_tolerates_unwritable_storage(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """目录不可写（只读盘 / 权限不足）时，加载仍返回默认值，不抛异常。"""

    def _fail_write(payload: dict) -> None:  # type: ignore[type-arg]
        raise ConfigIOError("disk denied")

    monkeypatch.setattr(store, "_write", _fail_write)
    with caplog.at_level(logging.WARNING, logger="emowall.config"):
        settings = store.load()

    assert settings == AppSettings()
    assert not store.path.exists()
    assert "could not write" in caplog.text


def test_save_raises_io_error_when_disk_fails(
    store: ConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_write(payload: dict) -> None:  # type: ignore[type-arg]
        raise ConfigIOError("disk denied")

    monkeypatch.setattr(store, "_write", _fail_write)
    with pytest.raises(ConfigIOError):
        store.save(AppSettings())
