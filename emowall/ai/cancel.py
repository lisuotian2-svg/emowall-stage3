"""线程安全的取消令牌。

语义：
    * `cancel()` 可从任意线程调用，置位取消标志并关闭已注册的资源
      （当前是 `httpx.Response`，从而中断正在阻塞的读取）；
    * 已取消时再注册资源，会立即关闭该资源，避免「取消发生在注册前」的竞态；
    * `reset()` 仅在生成器和取消清理均结束后允许复用令牌；
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
        self._active_generations = 0
        self._cancelling = False

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
            self._cancelling = True

        try:
            for closer in closers:
                self._safe_close(closer)
        finally:
            with self._lock:
                self._cancelling = False

    def reset(self) -> None:
        """清除取消状态，供下一轮生成复用。

        生成器（含异常分类）、资源登记或取消清理尚未结束时抛
        `RuntimeError`。cancel() 只是发起取消，调用方仍须等待旧生成退出。
        """
        with self._lock:
            if self._active_generations or self._closers or self._cancelling:
                raise RuntimeError("有活动生成或取消清理时不能 reset CancelToken；请等待生成结束")
            self._event.clear()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError("生成已取消")

    # ------------------------------------------------------------------
    # 供传输层使用的内部登记接口
    # ------------------------------------------------------------------

    def _begin_generation(self) -> None:
        """原子检查取消并登记生命周期，覆盖尚无响应资源的阶段。"""
        with self._lock:
            self.raise_if_cancelled()
            self._active_generations += 1

    def _end_generation(self) -> None:
        with self._lock:
            self._active_generations -= 1

    def _register(self, closer: Callable[[], None]) -> None:
        """登记一个随取消而执行的清理函数。

        若令牌已取消，立刻执行清理函数，保证竞态下资源也会被释放。
        """
        with self._lock:
            self._closers.add(closer)
            if not self._event.is_set():
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
