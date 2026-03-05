"""
파이프라인 오케스트레이터.
Hunk 추출 → Stage 1 (탐지) → Stage 2 (검증) → 코멘트 게시 전체 흐름을 관리한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from review_bot.config import settings
from review_bot.gitlab.client import GitLabClient, MRInfo
from review_bot.gitlab.commenter import GitLabCommenter
from review_bot.models.hunk import Hunk
from review_bot.models.issue import Issue, ValidatedIssue, Severity
from review_bot.agents import get_runner

logger = logging.getLogger(__name__)

SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


@dataclass
class ReviewResult:
    """리뷰 실행 결과."""
    mr_info: MRInfo
    total_hunks: int
    total_issues_found: int
    false_positives: int
    issues_posted: int
    issues: list[ValidatedIssue] = field(default_factory=list)


async def run_review(
    mr_id: int,
    repo_root: Path,
    dry_run: bool = False,
    severity_threshold: Severity = Severity.MEDIUM,
    max_concurrent: int = 4,
) -> ReviewResult:
    """전체 리뷰 파이프라인을 실행한다."""
    client = GitLabClient()

    # 1. MR 정보 + Hunk 추출
    mr_info = client.get_mr_info(mr_id)
    hunks = client.get_hunks(mr_id)
    logger.info(f"MR !{mr_id} '{mr_info.title}': {len(hunks)}개 hunk 추출")

    if not hunks:
        return ReviewResult(
            mr_info=mr_info,
            total_hunks=0,
            total_issues_found=0,
            false_positives=0,
            issues_posted=0,
        )

    # 2. Stage 1: Issue Identification (병렬)
    runner = get_runner()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_identify(hunk: Hunk) -> list[Issue]:
        async with semaphore:
            return await runner.identify_issues(hunk)

    stage1_results = await asyncio.gather(
        *[bounded_identify(h) for h in hunks],
        return_exceptions=True,
    )

    all_issues: list[Issue] = []
    for result in stage1_results:
        if isinstance(result, list):
            all_issues.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"Stage 1 exception: {result}")

    logger.info(f"Stage 1 완료: {len(all_issues)}개 잠재적 이슈 탐지")

    if not all_issues:
        if not dry_run:
            commenter = GitLabCommenter(client)
            commenter.post_review(mr_id, mr_info, [])
        return ReviewResult(
            mr_info=mr_info,
            total_hunks=len(hunks),
            total_issues_found=0,
            false_positives=0,
            issues_posted=0,
        )

    # 3. Stage 2: Issue Validation (병렬)
    async def bounded_validate(issue: Issue) -> ValidatedIssue:
        async with semaphore:
            return await runner.validate_issue(issue, repo_root)

    stage2_results = await asyncio.gather(
        *[bounded_validate(i) for i in all_issues],
        return_exceptions=True,
    )

    validated: list[ValidatedIssue] = []
    for result in stage2_results:
        if isinstance(result, ValidatedIssue):
            validated.append(result)
        elif isinstance(result, Exception):
            logger.error(f"Stage 2 exception: {result}")

    # 4. 필터링: false positive 제거 + severity 필터
    threshold_rank = SEVERITY_RANK[severity_threshold]
    real_issues = [
        v for v in validated
        if not v.is_false_positive
        and SEVERITY_RANK[v.severity] >= threshold_rank
    ]
    false_positive_count = sum(1 for v in validated if v.is_false_positive)

    logger.info(
        f"Stage 2 완료: {len(validated)}개 검증, "
        f"{false_positive_count}개 FP, "
        f"{len(real_issues)}개 실제 이슈"
    )

    # 5. 코멘트 게시
    if not dry_run:
        commenter = GitLabCommenter(client)
        commenter.post_review(mr_id, mr_info, real_issues)

    return ReviewResult(
        mr_info=mr_info,
        total_hunks=len(hunks),
        total_issues_found=len(all_issues),
        false_positives=false_positive_count,
        issues_posted=len(real_issues),
        issues=real_issues,
    )
