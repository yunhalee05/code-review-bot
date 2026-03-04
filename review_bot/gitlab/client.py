"""
GitLab MR에서 Hunk를 추출하는 클라이언트.
에이전트를 사용하지 않고 순수 API 호출만 사용 (토큰 절감).
"""

import re
import logging
from dataclasses import dataclass

import gitlab
from gitlab.v4.objects import ProjectMergeRequest

from review_bot.config import settings
from review_bot.models.hunk import Hunk

logger = logging.getLogger(__name__)

# 리뷰 대상에서 제외할 파일 패턴
SKIP_PATTERNS = [
    r".*\.lock$",
    r".*\.min\.js$",
    r".*\.min\.css$",
    r".*migrations/.*",
    r".*__pycache__/.*",
    r".*\.pyc$",
    r".*vendor/.*",
    r".*node_modules/.*",
    r".*\.generated\.",
]


@dataclass
class MRInfo:
    mr_id: int
    title: str
    description: str
    source_branch: str
    target_branch: str
    author: str
    url: str


class GitLabClient:
    def __init__(self):
        self._gl = gitlab.Gitlab(
            url=settings.gitlab_url,
            private_token=settings.gitlab_token,
        )
        self._project = self._gl.projects.get(settings.gitlab_project_id)

    def get_mr_info(self, mr_id: int) -> MRInfo:
        mr: ProjectMergeRequest = self._project.mergerequests.get(mr_id)
        return MRInfo(
            mr_id=mr_id,
            title=mr.title,
            description=mr.description or "",
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            author=mr.author["name"],
            url=mr.web_url,
        )

    def get_hunks(self, mr_id: int) -> list[Hunk]:
        """MR의 모든 변경을 Hunk 단위로 추출 (에이전트 X, 순수 파싱)"""
        mr: ProjectMergeRequest = self._project.mergerequests.get(mr_id)
        diffs = mr.diffs.list(get_all=True)

        if not diffs:
            logger.warning(f"MR {mr_id}: diff 없음")
            return []

        latest_diff = diffs[0]
        diff_details = mr.diffs.get(latest_diff.id)

        all_hunks: list[Hunk] = []
        file_count = 0

        for diff_file in diff_details.diffs:
            file_path = diff_file["new_path"]
            old_path = diff_file["old_path"]

            if self._should_skip(file_path):
                logger.debug(f"스킵: {file_path}")
                continue

            if file_count >= settings.max_files_per_mr:
                logger.warning(f"최대 파일 수 초과 ({settings.max_files_per_mr}), 이후 파일 스킵")
                break

            if diff_file.get("deleted_file", False):
                logger.debug(f"삭제된 파일 스킵: {file_path}")
                continue

            raw_diff = diff_file.get("diff", "")
            if not raw_diff:
                continue

            hunks = self._parse_hunks(raw_diff, file_path, old_path)
            all_hunks.extend(hunks[: settings.max_hunks_per_file])
            file_count += 1

        logger.info(f"MR {mr_id}: {file_count}개 파일, {len(all_hunks)}개 hunk 추출")
        return all_hunks

    def _parse_hunks(self, raw_diff: str, file_path: str, old_path: str) -> list[Hunk]:
        """raw diff 문자열을 Hunk 객체 리스트로 파싱"""
        hunks: list[Hunk] = []
        hunk_header_re = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@", re.MULTILINE)

        parts = hunk_header_re.split(raw_diff)
        headers = list(hunk_header_re.finditer(raw_diff))

        hunk_bodies = []
        i = 1
        while i < len(parts):
            new_start = int(parts[i])
            new_count_str = parts[i + 1]
            new_count = int(new_count_str) if new_count_str else 1
            body = parts[i + 2] if i + 2 < len(parts) else ""
            hunk_bodies.append((new_start, new_count, body))
            i += 3

        for header_match, (new_start, new_count, body) in zip(headers, hunk_bodies):
            added = [l[1:] for l in body.splitlines() if l.startswith("+")]
            removed = [l[1:] for l in body.splitlines() if l.startswith("-")]

            if not added and not removed:
                continue

            hunks.append(
                Hunk(
                    file_path=file_path,
                    old_path=old_path,
                    new_start_line=new_start,
                    new_line_count=new_count,
                    content=header_match.group(0) + body,
                    added_lines=added,
                    removed_lines=removed,
                )
            )

        return hunks

    def _should_skip(self, file_path: str) -> bool:
        return any(re.match(pattern, file_path) for pattern in SKIP_PATTERNS)