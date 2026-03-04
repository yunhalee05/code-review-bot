"""
Stage 2: Issue Validation 에이전트.
코드베이스 레퍼런스를 기반으로 이슈의 진위를 검증한다.
Claude와 OpenAI 프로바이더를 모두 지원한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from review_bot.config import settings
from review_bot.models.issue import Issue, ValidatedIssue
from review_bot.tools.storage import (
    ValidationStorage,
    create_validation_storage_server,
    create_validation_openai_tools,
)
from review_bot.tools.codebase import (
    create_codebase_server,
    create_codebase_openai_tools,
)
from review_bot.prompts.validate import VALIDATE_SYSTEM_PROMPT, VALIDATE_USER_PROMPT
from review_bot.agents.base import run_agent

logger = logging.getLogger(__name__)


async def validate_issue(issue: Issue, repo_root: Path) -> ValidatedIssue:
    """단일 이슈를 코드베이스 레퍼런스 기반으로 검증한다."""
    storage = ValidationStorage(issue=issue)

    prompt = VALIDATE_USER_PROMPT.format(
        file_path=issue.file_path,
        line_number=issue.line_number,
        code=issue.code,
        title=issue.title,
        severity=issue.severity.value,
        description=issue.description,
        hunk_content=issue.hunk_content,
    )

    # 프로바이더별 도구 준비
    mcp_servers = None
    allowed_tools = None
    openai_tools = None

    if settings.review_provider == "openai":
        openai_tools = (
            create_validation_openai_tools(storage)
            + create_codebase_openai_tools(repo_root)
        )
    else:
        validation_server = create_validation_storage_server(storage)
        codebase_server = create_codebase_server(repo_root)
        mcp_servers = {
            "validation": validation_server,
            "codebase": codebase_server,
        }
        allowed_tools = [
            "mcp__validation__submit_validated_issue",
            "mcp__codebase__search_code",
            "mcp__codebase__read_file_lines",
            "mcp__codebase__list_directory",
        ]

    try:
        await run_agent(
            prompt=prompt,
            system_prompt=VALIDATE_SYSTEM_PROMPT,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            openai_tools=openai_tools,
            max_turns=15,
        )
    except Exception:
        logger.exception(f"Stage 2 failed for {issue.code}: {issue.title}")
        return _fallback(issue, "Agent execution failed")

    if storage.result is not None:
        fp_label = "FP" if storage.result.is_false_positive else "REAL"
        logger.info(f"Stage 2: {issue.code} → {fp_label}")
        return storage.result

    return _fallback(issue, "Agent did not submit validation result")


def _fallback(issue: Issue, reason: str) -> ValidatedIssue:
    """에이전트가 결과를 제출하지 않은 경우 보수적으로 실제 이슈로 처리."""
    logger.warning(f"Stage 2 fallback for {issue.code}: {reason}")
    return ValidatedIssue(
        issue=issue,
        is_false_positive=False,
        evidence=reason,
        mitigation="",
        suggestion="Manual review recommended.",
        references=[],
    )
