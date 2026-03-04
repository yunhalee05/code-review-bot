"""
멀티 프로바이더 Agent SDK 래퍼.
Claude Agent SDK와 OpenAI Agents SDK를 동일한 인터페이스로 실행한다.
"""

from __future__ import annotations

import logging
from typing import Any

from review_bot.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Claude Agent SDK
# ---------------------------------------------------------------------------

async def run_claude_agent(
    prompt: str,
    system_prompt: str,
    mcp_servers: dict[str, Any],
    allowed_tools: list[str],
    model: str | None = None,
    max_turns: int = 10,
) -> str | None:
    """Claude Agent SDK로 에이전트를 실행한다."""
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model or settings.review_model,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
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


# ---------------------------------------------------------------------------
# OpenAI Agents SDK
# ---------------------------------------------------------------------------

async def run_openai_agent(
    prompt: str,
    system_prompt: str,
    tools: list[Any],
    model: str | None = None,
    max_turns: int = 10,
) -> str | None:
    """OpenAI Agents SDK로 에이전트를 실행한다."""
    from agents import Agent, Runner

    agent = Agent(
        name="review-bot",
        instructions=system_prompt,
        tools=tools,
        model=model or settings.openai_review_model,
    )

    try:
        result = await Runner.run(
            agent,
            prompt,
            max_turns=max_turns,
        )
        return result.final_output
    except Exception:
        logger.exception("OpenAI agent execution failed")
        raise


# ---------------------------------------------------------------------------
# 통합 디스패처
# ---------------------------------------------------------------------------

async def run_agent(
    prompt: str,
    system_prompt: str,
    # Claude 전용
    mcp_servers: dict[str, Any] | None = None,
    allowed_tools: list[str] | None = None,
    # OpenAI 전용
    openai_tools: list[Any] | None = None,
    # 공통
    model: str | None = None,
    max_turns: int = 10,
    provider: str | None = None,
) -> str | None:
    """설정된 프로바이더에 따라 적절한 Agent SDK를 호출한다.

    구조화된 데이터는 tool call을 통해 storage 객체에 직접 수집되므로,
    반환되는 텍스트는 로깅/디버깅 용도로만 사용한다.
    """
    active_provider = provider or settings.review_provider

    if active_provider == "openai":
        if not openai_tools:
            raise ValueError("OpenAI 프로바이더에는 openai_tools가 필요합니다")
        return await run_openai_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            tools=openai_tools,
            model=model,
            max_turns=max_turns,
        )
    else:
        if not mcp_servers:
            raise ValueError("Claude 프로바이더에는 mcp_servers가 필요합니다")
        return await run_claude_agent(
            prompt=prompt,
            system_prompt=system_prompt,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools or [],
            model=model,
            max_turns=max_turns,
        )
