"""Claude Agent SDK 기반 에이전트 실행기."""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions, ResultMessage

from review_bot.agents.toolkit import ToolKit, ToolDefinition
from review_bot.config import settings

logger = logging.getLogger(__name__)


def _to_mcp_server(toolkit: ToolKit):
    """ToolDefinition 리스트를 Claude MCP 서버로 변환한다."""
    mcp_tools = []
    for defn in toolkit.tools:
        # 클로저로 handler 캡처
        handler = defn.handler

        @tool(defn.name, defn.description, defn.schema)
        async def _wrapped(args: dict[str, Any], _handler=handler) -> dict[str, Any]:
            result = await _handler(args)
            return {"content": [{"type": "text", "text": result}]}

        mcp_tools.append(_wrapped)

    return create_sdk_mcp_server(name="tools", version="1.0.0", tools=mcp_tools)


class ClaudeAgentRunner:
    """Claude Agent SDK로 에이전트를 실행한다."""

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        toolkit: ToolKit,
        max_turns: int = 10,
    ) -> str | None:
        server = _to_mcp_server(toolkit)
        allowed = [f"mcp__tools__{defn.name}" for defn in toolkit.tools]

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
