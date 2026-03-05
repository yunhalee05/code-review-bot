"""AgentRunner 추상 클래스 + 팩토리."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TYPE_CHECKING

from review_bot.config import settings

if TYPE_CHECKING:
    from review_bot.agents.toolkit import ToolKit
    from review_bot.models.hunk import Hunk
    from review_bot.models.issue import Issue, ValidatedIssue

logger = logging.getLogger(__name__)


class AgentRunner(ABC):
    """에이전트 실행기의 공통 인터페이스."""

    @abstractmethod
    def _to_tools(self, toolkit: ToolKit) -> Any:
        """ToolKit을 SDK 네이티브 도구 형식으로 변환한다."""

    @abstractmethod
    async def run(
        self,
        prompt: str,
        system_prompt: str,
        toolkit: ToolKit,
        max_turns: int = 10,
    ) -> str | None:
        """에이전트를 실행하고 결과 텍스트를 반환한다.

        구조화된 데이터는 tool call을 통해 storage 객체에 직접 수집되므로,
        반환되는 텍스트는 로깅/디버깅 용도로만 사용한다.
        """

    async def identify_issues(self, hunk: Hunk) -> list[Issue]:
        """Stage 1: 단일 Hunk를 분석하여 잠재적 이슈 목록을 반환한다."""
        from review_bot.tools.storage import IssueStorage
        from review_bot.prompts.identify import IDENTIFY_SYSTEM_PROMPT, IDENTIFY_USER_PROMPT

        storage = IssueStorage(file_path=hunk.file_path)
        toolkit = storage.to_toolkit()

        prompt = IDENTIFY_USER_PROMPT.format(
            file_path=hunk.file_path,
            start_line=hunk.new_start_line,
            extension=hunk.file_extension,
            hunk_content=hunk.content,
        )

        try:
            await self.run(prompt, IDENTIFY_SYSTEM_PROMPT, toolkit, max_turns=5)
        except Exception:
            logger.exception(f"Stage 1 failed for {hunk.summary}")
            return []

        for issue in storage.issues:
            issue.hunk_content = hunk.content

        logger.info(f"Stage 1: {hunk.summary} → {len(storage.issues)}개 이슈 탐지")
        return storage.issues

    async def validate_issue(self, issue: Issue, repo_root: Path) -> ValidatedIssue:
        """Stage 2: 단일 이슈를 로컬 코드베이스 기반으로 검증한다."""
        from review_bot.models.issue import ValidatedIssue
        from review_bot.tools.storage import ValidationStorage
        from review_bot.tools.codebase import CodebaseSearcher
        from review_bot.prompts.validate import VALIDATE_SYSTEM_PROMPT, VALIDATE_USER_PROMPT

        storage = ValidationStorage(issue=issue)
        searcher = CodebaseSearcher(repo_root)
        toolkit = storage.to_toolkit().merge(searcher.to_toolkit())

        prompt = VALIDATE_USER_PROMPT.format(
            file_path=issue.file_path,
            line_number=issue.line_number,
            code=issue.code,
            title=issue.title,
            severity=issue.severity.value,
            description=issue.description,
            hunk_content=issue.hunk_content,
        )

        try:
            await self.run(prompt, VALIDATE_SYSTEM_PROMPT, toolkit, max_turns=15)
        except Exception:
            logger.exception(f"Stage 2 failed for {issue.code}: {issue.title}")
            return self._fallback(issue, "Agent execution failed")

        if storage.result is not None:
            fp_label = "FP" if storage.result.is_false_positive else "REAL"
            logger.info(f"Stage 2: {issue.code} → {fp_label}")
            return storage.result

        return self._fallback(issue, "Agent did not submit validation result")

    @staticmethod
    def _fallback(issue: Issue, reason: str) -> ValidatedIssue:
        """에이전트가 결과를 제출하지 않은 경우 보수적으로 실제 이슈로 처리."""
        from review_bot.models.issue import ValidatedIssue

        logger.warning(f"Stage 2 fallback for {issue.code}: {reason}")
        return ValidatedIssue(
            issue=issue,
            is_false_positive=False,
            evidence=reason,
            mitigation="",
            suggestion="Manual review recommended.",
            references=[],
        )


_runner_instance: AgentRunner | None = None


def get_runner(provider: str | None = None) -> AgentRunner:
    """설정된 프로바이더에 맞는 AgentRunner 싱글턴 인스턴스를 반환한다."""
    global _runner_instance
    if _runner_instance is not None and provider is None:
        return _runner_instance

    active = provider or settings.review_provider
    if active == "openai":
        from review_bot.agents.openai_runner import OpenAIAgentRunner
        runner = OpenAIAgentRunner()
    else:
        from review_bot.agents.claude_runner import ClaudeAgentRunner
        runner = ClaudeAgentRunner()

    if provider is None:
        _runner_instance = runner
    return runner
