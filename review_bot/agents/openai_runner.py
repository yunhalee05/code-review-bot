"""OpenAI Agents SDK 기반 에이전트 실행기."""

from __future__ import annotations

import json
import logging

from agents import Agent, Runner, FunctionTool

from review_bot.agents.toolkit import ToolKit, ToolDefinition
from review_bot.config import settings

logger = logging.getLogger(__name__)


def _to_function_tools(toolkit: ToolKit) -> list[FunctionTool]:
    """ToolDefinition 리스트를 OpenAI FunctionTool로 변환한다."""
    tools = []
    for defn in toolkit.tools:
        handler = defn.handler

        async def _invoke(ctx, args_json: str, _handler=handler) -> str:
            args = json.loads(args_json)
            return await _handler(args)

        ft = FunctionTool(
            name=defn.name,
            description=defn.description,
            params_json_schema=defn.schema,
            on_invoke_tool=_invoke,
        )
        tools.append(ft)
    return tools


class OpenAIAgentRunner:
    """OpenAI Agents SDK로 에이전트를 실행한다."""

    async def run(
        self,
        prompt: str,
        system_prompt: str,
        toolkit: ToolKit,
        max_turns: int = 10,
    ) -> str | None:
        agent = Agent(
            name="review-bot",
            instructions=system_prompt,
            tools=_to_function_tools(toolkit),
            model=settings.openai_review_model,
        )

        try:
            result = await Runner.run(agent, prompt, max_turns=max_turns)
            return result.final_output
        except Exception:
            logger.exception("OpenAI agent execution failed")
            raise
