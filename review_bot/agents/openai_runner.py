"""OpenAI Agents SDK 기반 에이전트 실행기."""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from agents import Agent, Runner, FunctionTool

from review_bot.agents.toolkit import ToolKit, ToolDefinition
from review_bot.config import settings

logger = logging.getLogger(__name__)


class OpenAIAgentRunner:
    """OpenAI Agents SDK로 에이전트를 실행한다."""

    @staticmethod
    def _make_invoke(handler: Callable[[dict], Awaitable[str]]):
        """ToolDefinition handler를 OpenAI on_invoke_tool 시그니처로 변환한다."""
        async def invoke(ctx: Any, args_json: str) -> str:
            return await handler(json.loads(args_json))
        return invoke

    def _to_tools(self, toolkit: ToolKit) -> list[FunctionTool]:
        return [
            FunctionTool(
                name=defn.name,
                description=defn.description,
                params_json_schema=defn.schema,
                on_invoke_tool=self._make_invoke(defn.handler),
            )
            for defn in toolkit.tools
        ]

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
            tools=self._to_tools(toolkit),
            model=settings.openai_review_model,
        )

        try:
            result = await Runner.run(agent, prompt, max_turns=max_turns)
            return result.final_output
        except Exception:
            logger.exception("OpenAI agent execution failed")
            raise
