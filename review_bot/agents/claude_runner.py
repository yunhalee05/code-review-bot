"""Claude Agent SDK 기반 에이전트 실행기."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions, ResultMessage

from review_bot.agents.toolkit import ToolKit, ToolDefinition
from review_bot.config import settings

logger = logging.getLogger(__name__)


class ClaudeAgentRunner:
    """Claude Agent SDK로 에이전트를 실행한다."""

    @staticmethod
    def _make_mcp_tool(defn: ToolDefinition):
        """단일 ToolDefinition을 Claude MCP tool로 변환한다."""
        handler = defn.handler
        @tool(defn.name, defn.description, defn.schema)
        async def wrapped(args: dict[str, Any], _handler: Callable = handler) -> dict[str, Any]:
            result = await _handler(args)
            return {"content": [{"type": "text", "text": result}]}
        return wrapped

    def _to_tools(self, toolkit: ToolKit):
        mcp_tools = [self._make_mcp_tool(defn) for defn in toolkit.tools]
        server = create_sdk_mcp_server(name="tools", version="1.0.0", tools=mcp_tools)
        allowed = [f"mcp__tools__{defn.name}" for defn in toolkit.tools]
        return server, allowed

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        toolkit: ToolKit,
        max_turns: int = 10,
    ) -> str | None:
        server, allowed = self._to_tools(toolkit)

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=settings.review_model,
            mcp_servers={"tools": server},
            allowed_tools=allowed,
            max_turns=max_turns,
        )

        result_text = None
        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    result_text = message.result
        except Exception:
            logger.exception("Claude agent execution failed")
            raise

        return result_text
