"""配置文件读写：原子写入、损坏恢复、未知字段保留、版本兼容。

策略一览：
    * 文件缺失      → 用默认值并生成 `config.json`
    * JSON 损坏     → 备份为 `config.<时间戳>.corrupt-*.json` 后恢复默认（备份失败则不覆盖原文件）
    * 字段非法      → 该字段回退默认值并记录 warning，**不重写用户文件**
    * 未知字段      → 忽略（作用于运行时），但保存时原样保留，兼容未来版本
    * 版本较新/较旧 → 兼容读取已知字段并记录 warning
    * 写入          → 同目录临时文件 + fsync + `os.replace` 原子替换
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ConfigIOError, ConfigValidationError
from .paths import config_path
from .settings import (
    CHAT_FIELD_VALIDATORS,
    CURRENT_CONFIG_VERSION,
    OLLAMA_FIELD_VALIDATORS,
    AppSettings,
    ChatSettings,
    OllamaSettings,
    default_settings,
)

logger = logging.getLogger("emowall.config.store")

KNOWN_TOP_LEVEL_FIELDS = frozenset({"version", "ollama", "chat"})


class ConfigStore:
    """一个配置文件的读写入口。

    线程归属由调用方保证：配置只在应用启动与「保存设置」时使用，
    不参与高频并发；本类不创建线程、不加锁。
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else config_path()
        self._raw: dict[str, Any] = {}
        self._raw_loaded = False

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load(self) -> AppSettings:
        """读取配置；任何文件问题都降级为默认值，不向上抛异常。"""
        self._raw_loaded = False

        if not self._path.exists():
            logger.info("config not found, creating defaults: %s", self._path)
            self._raw = {}
            self._raw_loaded = True
            settings = default_settings()
            self._try_write(settings)
            return settings

        try:
            # utf-8-sig：兼容 Windows 记事本可能写入的 BOM
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, RecursionError) as exc:
            logger.warning("config unreadable, will back up and reset (%s): %s", self._path, exc)
            return self._recover_corrupt()

        if not isinstance(raw, dict):
            logger.warning("config root must be a JSON object, got %s", type(raw).__name__)
            return self._recover_corrupt()

        self._raw = raw
        self._raw_loaded = True
        return self._parse(raw)

    def _recover_corrupt(self) -> AppSettings:
        backup = self._backup_corrupt()
        self._raw = {}
        self._raw_loaded = True
        settings = default_settings()
        if backup is not None:
            # 只有原文件已安全挪走，才写回默认配置，避免覆盖用户数据
            self._try_write(settings)
        return settings

    def _backup_corrupt(self) -> Path | None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        candidate = self._path.with_name(f"{self._path.stem}.corrupt-{stamp}{self._path.suffix}")
        index = 1
        while candidate.exists():
            candidate = self._path.with_name(
                f"{self._path.stem}.corrupt-{stamp}-{index}{self._path.suffix}"
            )
            index += 1
        try:
            os.replace(self._path, candidate)
        except OSError as exc:
            logger.warning("could not back up corrupt config %s: %s", self._path, exc)
            return None
        logger.warning("corrupt config backed up to %s", candidate)
        return candidate

    def _parse(self, raw: dict[str, Any]) -> AppSettings:
        self._log_version(raw.get("version"))

        ollama_raw = self._section_object(raw, "ollama")
        chat_raw = self._section_object(raw, "chat")
        self._log_unknown_fields(raw, ollama_raw, chat_raw)

        ollama = OllamaSettings(
            **self._section_kwargs("ollama", ollama_raw, OllamaSettings(), OLLAMA_FIELD_VALIDATORS)
        )
        chat = ChatSettings(
            **self._section_kwargs("chat", chat_raw, ChatSettings(), CHAT_FIELD_VALIDATORS)
        )
        return AppSettings(ollama=ollama, chat=chat)

    @staticmethod
    def _log_version(version: object) -> None:
        if version is None:
            logger.warning("config 'version' missing; assuming %d", CURRENT_CONFIG_VERSION)
        elif isinstance(version, bool) or not isinstance(version, int):
            logger.warning(
                "config 'version' must be an integer (got %r); assuming %d",
                version,
                CURRENT_CONFIG_VERSION,
            )
        elif version > CURRENT_CONFIG_VERSION:
            logger.warning(
                "config version %d is newer than supported %d; reading known fields only",
                version,
                CURRENT_CONFIG_VERSION,
            )
        elif version < CURRENT_CONFIG_VERSION:
            logger.warning(
                "config version %d is older than %d; missing fields use defaults",
                version,
                CURRENT_CONFIG_VERSION,
            )

    @staticmethod
    def _section_object(raw: dict[str, Any], name: str) -> dict[str, Any]:
        value = raw.get(name, {})
        if value is None:
            return {}
        if not isinstance(value, dict):
            logger.warning(
                "config section '%s' must be an object, got %s; using defaults",
                name,
                type(value).__name__,
            )
            return {}
        return value

    @staticmethod
    def _log_unknown_fields(
        raw: dict[str, Any], ollama_raw: dict[str, Any], chat_raw: dict[str, Any]
    ) -> None:
        unknown = sorted(set(raw) - KNOWN_TOP_LEVEL_FIELDS)
        unknown += [f"ollama.{key}" for key in sorted(set(ollama_raw) - set(OLLAMA_FIELD_VALIDATORS))]
        unknown += [f"chat.{key}" for key in sorted(set(chat_raw) - set(CHAT_FIELD_VALIDATORS))]
        if unknown:
            logger.warning(
                "unknown config fields ignored at runtime (preserved on save): %s",
                ", ".join(unknown),
            )

    @staticmethod
    def _section_kwargs(
        section: str,
        raw: dict[str, Any],
        defaults: Any,
        validators: dict[str, Callable[[object], Any]],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for name, validator in validators.items():
            default = getattr(defaults, name)
            if name not in raw:
                kwargs[name] = default
                continue
            try:
                kwargs[name] = validator(raw[name])
            except ConfigValidationError:
                logger.warning(
                    "invalid value for %s.%s; using default",
                    section,
                    name,
                )
                kwargs[name] = default
        return kwargs

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save(self, settings: AppSettings) -> None:
        """原子写入配置；`settings` 在构造时已完成字段校验。"""
        if not isinstance(settings, AppSettings):
            raise ConfigValidationError("settings: 必须是 AppSettings 实例")

        if not self._raw_loaded:
            self._prime_raw()
        payload = self._payload(settings)
        self._write(payload)
        self._raw = payload
        self._raw_loaded = True
        logger.info("config saved: %s", self._path)

    def _prime_raw(self) -> None:
        """未 load 就 save 时，尽力读取旧内容以保留未知字段。"""
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, RecursionError):
            return
        if isinstance(raw, dict):
            self._raw = raw

    def _payload(self, settings: AppSettings) -> dict[str, Any]:
        payload: dict[str, Any] = dict(self._raw)

        ollama_existing = payload.get("ollama")
        chat_existing = payload.get("chat")
        payload["version"] = CURRENT_CONFIG_VERSION
        payload["ollama"] = {
            **(ollama_existing if isinstance(ollama_existing, dict) else {}),
            **asdict(settings.ollama),
        }
        payload["chat"] = {
            **(chat_existing if isinstance(chat_existing, dict) else {}),
            **asdict(settings.chat),
        }
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f"{self._path.name}.", suffix=".tmp", dir=parent
            )
        except OSError as exc:
            raise ConfigIOError(f"无法创建配置临时文件：{self._path}（{exc}）") from exc

        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
        except OSError as exc:
            raise ConfigIOError(f"写入配置失败：{self._path}（{exc}）") from exc
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:  # 清理失败不影响主流程
                    logger.debug("could not remove temp config file: %s", temp_path)

    def _try_write(self, settings: AppSettings) -> None:
        try:
            self._write(self._payload(settings))
        except ConfigIOError as exc:
            logger.warning("could not write default config: %s", exc)
