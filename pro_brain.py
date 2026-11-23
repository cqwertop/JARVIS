"""Runs JARVIS on your Claude Pro/Max plan, through Claude Code, instead of a paid API key.

Uses the Claude Agent SDK, which drives the Claude Code program installed on this PC and its sign-in.
Requests count toward your plan's usage limits (shared with claude.ai and Claude Code).
Built for personal use: Anthropic doesn't allow apps given to other people to run on someone's plan sign-in.
"""

import asyncio
import threading

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

import tools

SERVER_NAME = "jarvis"


def _wrap(beta_tool):
    """Turn one of our @beta_tool functions into a tool Claude Code can call."""

    @tool(beta_tool.name, beta_tool.description, beta_tool.input_schema)
    async def handler(args):
        try:
            # Run in a thread so slow tools (weather, app search) don't block the event loop.
            result = await asyncio.to_thread(beta_tool.call, args)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Error: {exc}"}], "is_error": True}

    return handler


class ProBrain:
    """Same interface as main.Brain: ask(text) -> spoken reply. Keeps one Claude Code session open."""

    def __init__(self, model: str, system_prompt: str):
        server = create_sdk_mcp_server(SERVER_NAME, tools=[_wrap(t) for t in tools.ALL_TOOLS])
        allowed = [f"mcp__{SERVER_NAME}__{t.name}" for t in tools.ALL_TOOLS] + ["WebSearch", "WebFetch"]
        self._options = ClaudeAgentOptions(
            model=model,
            system_prompt=system_prompt,
            mcp_servers={SERVER_NAME: server},
            tools=["WebSearch", "WebFetch"],  # no file editing or shell commands - only JARVIS's own tools
            allowed_tools=allowed,
            permission_mode="dontAsk",  # anything not in allowed_tools is refused, never prompted
            setting_sources=[],  # don't load your personal Claude Code settings/CLAUDE.md
            max_turns=12,
        )
        # The SDK is async; run it on its own background event loop so main.py can stay simple.
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._client: ClaudeSDKClient | None = None
        self._run(self._connect())

    def _run(self, coro, timeout: float = 180):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _connect(self):
        self._client = ClaudeSDKClient(options=self._options)
        await self._client.connect()

    async def _ask(self, text: str) -> str:
        await self._client.query(text)
        parts: list[str] = []
        last_turn: list[str] = []
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                texts = [b.text for b in msg.content if isinstance(b, TextBlock)]
                if texts:
                    last_turn = texts
                    parts.extend(texts)
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    detail = msg.result or ", ".join(msg.errors or []) or msg.subtype
                    raise RuntimeError(detail)
                if msg.result:
                    return msg.result
        return " ".join(last_turn or parts)

    def ask(self, text: str) -> str:
        try:
            return self._run(self._ask(text))
        except Exception as exc:
            if "limit" in str(exc).lower():
                raise  # usage limit - reconnecting won't help
            # JARVIS runs for days; if the Claude Code process died, start a fresh one and try once more.
            print(f"[Claude Code session lost ({exc!r}); reconnecting]")
            self.close()
            self._run(self._connect())
            return self._run(self._ask(text))

    def close(self):
        if self._client:
            try:
                self._run(self._client.disconnect(), timeout=10)
            except Exception:
                pass
