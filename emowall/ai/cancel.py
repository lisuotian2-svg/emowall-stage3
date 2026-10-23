"""线程安全的取消令牌。

语义：
    * `cancel()` 可从任意线程调用，置位取消标志并关闭已注册的资源
      （当前是 `httpx.Response`，从而中断正在阻塞的读取）；
    * 已取消时再注册资源，会立即关闭该资源，避免「取消发生在注册前」的竞态；
    * `reset()` 用于复用令牌，调用方必须保证此时没有正在进行的生成；
    * 取消不是网络错误，客户端会把它映射为 `CancelledError`。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .errors import CancelledError

logger = logging.getLogger("emowall.ai.cancel")


class CancelToken:
    """跨线程取消信号 + 活动网络资源登记表。"""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._closers: set[Callable[[], None]] = set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        """请求取消；重复调用无副作用。"""
        with self._lock:
            if self._event.is_set():
                return
            self._event.set()
            closers = tuple(self._closers)
            self._closers.clear()

        for closer in closers:
            self._safe_close(closer)

    def reset(self) -> None:
        """清除取消状态，供下一轮生成复用。

        只允许在没有活动生成时调用：若仍有登记的响应/连接，直接抛
        `RuntimeError`，避免静默丢取消能力（调用方应先 cancel 或等待生成结束）。
        """
        with self._lock:
            if self._closers:
                raise RuntimeError("有活动生成时不能 reset CancelToken；请先 cancel 或等待生成结束")
            self._event.clear()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError("生成已取消")

    # ------------------------------------------------------------------
    # 供传输层使用的内部登记接口
    # ------------------------------------------------------------------

    def _register(self, closer: Callable[[], None]) -> None:
        """登记一个随取消而执行的清理函数。

        若令牌已取消，立刻执行清理函数，保证竞态下资源也会被释放。
        """
        with self._lock:
            if not self._event.is_set():
                self._closers.add(closer)
                return
        self._safe_close(closer)

    def _unregister(self, closer: Callable[[], None]) -> None:
        with self._lock:
            self._closers.discard(closer)

    @staticmethod
    def _safe_close(closer: Callable[[], None]) -> None:
        try:
            closer()
        except Exception:  # 关闭资源失败不应掩盖取消/原始错误
            logger.warning("关闭取消资源失败", exc_info=True)
