"""Ollama 命令行联调工具（Stage 2）。

用途：
    * 验证本机 Ollama 是否可用、模型是否已安装；
    * 逐块打印流式回复；
    * Ctrl+C 取消生成（不打印堆栈）；
    * 传入多个 --prompt 时模拟连续多轮对话。

示例：
    .\\.venv\\Scripts\\python.exe scripts\\chat_probe.py --prompt "你好"
    .\\.venv\\Scripts\\python.exe scripts\\chat_probe.py --list-models
    .\\.venv\\Scripts\\python.exe scripts\\chat_probe.py --prompt "记住 42" --prompt "我刚才说的数字？"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 以脚本方式运行时，把项目根目录加入 sys.path，保证 `import emowall` 可用。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from emowall.ai import (  # noqa: E402 - 路径修正后再导入
    AIError,
    CancelToken,
    ChatEngine,
    ChatMessage,
    OllamaClient,
)
from emowall.config import ConfigStore  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EmoWall AI Stage 2 Ollama 联调工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--prompt",
        action="append",
        default=None,
        help="用户消息；可重复传入以模拟多轮对话（默认：你好）",
    )
    parser.add_argument("--model", default=None, help="覆盖配置中的模型名")
    parser.add_argument("--base-url", default=None, help="覆盖配置中的 Ollama 地址")
    parser.add_argument("--system", default=None, help="覆盖配置中的系统提示词")
    parser.add_argument("--temperature", type=float, default=None, help="覆盖温度")
    parser.add_argument("--num-ctx", type=int, default=None, help="覆盖 num_ctx")
    parser.add_argument("--list-models", action="store_true", help="只列出已安装模型后退出")
    return parser


def _run(args: argparse.Namespace) -> int:
    settings = ConfigStore().load()
    ollama = settings.ollama
    base_url = args.base_url or ollama.base_url
    model = args.model or ollama.model
    system_prompt = args.system if args.system is not None else settings.chat.system_prompt
    temperature = ollama.temperature if args.temperature is None else args.temperature
    num_ctx = ollama.num_ctx if args.num_ctx is None else args.num_ctx

    client = OllamaClient(
        base_url,
        connect_timeout=ollama.connect_timeout_seconds,
        read_timeout=ollama.read_timeout_seconds,
    )
    try:
        if args.list_models:
            for name in client.list_models():
                print(name)
            return 0

        engine = ChatEngine(
            client,
            model=model,
            max_context_messages=settings.chat.max_context_messages,
            max_context_chars=settings.chat.max_context_chars,
            system_prompt=system_prompt,
            options={"num_ctx": num_ctx, "temperature": temperature},
            think=ollama.think,
        )

        prompts = args.prompt or ["你好"]
        history: list[ChatMessage] = []
        for prompt in prompts:
            history.append(ChatMessage("user", prompt))
            token = CancelToken()
            stream = engine.stream_reply(history, cancel=token)
            reply_parts: list[str] = []
            try:
                for chunk in stream:
                    if chunk.text:
                        reply_parts.append(chunk.text)
                        print(chunk.text, end="", flush=True)
            except KeyboardInterrupt:
                token.cancel()
                stream.close()
                print("\n[已取消]")
                return 130
            finally:
                stream.close()
            print()
            history.append(ChatMessage("assistant", "".join(reply_parts)))
        return 0
    except AIError as exc:
        print(f"[错误] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except KeyboardInterrupt:
        print("\n[已取消]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
