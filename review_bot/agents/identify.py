"""
Stage 1: Issue Identification 에이전트.
Hunk를 분석하여 잠재적 이슈를 공격적으로 탐지한다.
Claude와 OpenAI 프로바이더를 모두 지원한다.
"""

from __future__ import annotations

import logging

from review_bot.config import settings
from review_bot.models.hunk import Hunk
from review_bot.models.issue import Issue
from review_bot.tools.storage import (
    IssueStorage,
    create_issue_storage_server,
    create_issue_openai_tools,
)
from review_bot.prompts.identify import IDENTIFY_SYSTEM_PROMPT, IDENTIFY_USER_PROMPT
from review_bot.agents.base import run_agent

logger = logging.getLogger(__name__)


async def identify_issues(hunk: Hunk) -> list[Issue]:
    """단일 Hunk를 분석하여 잠재적 이슈 목록을 반환한다."""
    storage = IssueStorage(file_path=hunk.file_path)

    prompt = IDENTIFY_USER_PROMPT.format(
        file_path=hunk.file_path,
        start_line=hunk.new_start_line,
        extension=hunk.file_extension,
        hunk_content=hunk.content,
    )

    # 프로바이더별 도구 준비
    mcp_servers = None
    allowed_tools = None
    openai_tools = None

    if settings.review_provider == "openai":
        openai_tools = create_issue_openai_tools(storage)
    else:
        server = create_issue_storage_server(storage)
        mcp_servers = {"issue_storage": server}
        allowed_tools = ["mcp__issue_storage__report_issue"]

    try:
        await run_agent(
            prompt=prompt,
            system_prompt=IDENTIFY_SYSTEM_PROMPT,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            openai_tools=openai_tools,
            max_turns=5,
        )
    except Exception:
        logger.exception(f"Stage 1 failed for {hunk.summary}")
        return []

    # 검증 단계에서 사용할 원본 hunk 컨텍스트 첨부
    for issue in storage.issues:
        issue.hunk_content = hunk.content

    logger.info(f"Stage 1: {hunk.summary} → {len(storage.issues)}개 이슈 탐지")
    return storage.issues
