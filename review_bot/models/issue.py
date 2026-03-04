from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"   # 반드시 수정 (보안, 데이터 손실)
    HIGH = "high"           # 강력 권고 (버그, 트랜잭션 누락)
    MEDIUM = "medium"       # 권고 (성능, 코드 품질)
    LOW = "low"             # 참고 (스타일, 개선 제안)


@dataclass
class Issue:
    """STEP1 에이전트가 발견한 잠재적 이슈 (검증 전)"""

    file_path: str
    line_number: int        # MR diff 기준 줄 번호
    code: str               # 이슈 식별 코드 (예: SEC001, TXN002)
    title: str              # 한 줄 요약
    description: str        # 상세 설명
    severity: Severity
    hunk_content: str = ""  # 원본 hunk (검증 시 컨텍스트용)


@dataclass
class ValidatedIssue:
    """STEP2 에이전트가 레퍼런스 기반으로 검증한 이슈"""

    issue: Issue
    is_false_positive: bool
    evidence: str           # 실제 문제인 근거
    mitigation: str         # 오탐일 수 있는 근거
    suggestion: str         # 수정 제안 코드 or 방법
    references: list[str] = field(default_factory=list)  # 참조 파일/라인

    @property
    def file_path(self) -> str:
        return self.issue.file_path

    @property
    def line_number(self) -> int:
        return self.issue.line_number

    @property
    def severity(self) -> Severity:
        return self.issue.severity

    def format_comment(self) -> str:
        """GitLab 코멘트 마크다운 포맷"""
        severity_emoji = {
            Severity.CRITICAL: "🚨",
            Severity.HIGH: "🔴",
            Severity.MEDIUM: "🟡",
            Severity.LOW: "🔵",
        }
        emoji = severity_emoji.get(self.severity, "⚪")

        lines = [
            f"{emoji} **[{self.severity.value.upper()}] {self.issue.code}: {self.issue.title}**",
            "",
            f"**문제:** {self.issue.description}",
            "",
        ]

        if self.suggestion:
            lines += [
                "**수정 제안:**",
                f"```\n{self.suggestion}\n```",
                "",
            ]

        if self.evidence:
            lines += [f"**근거:** {self.evidence}", ""]

        if self.references:
            ref_text = ", ".join(f"`{r}`" for r in self.references)
            lines += [f"**참조:** {ref_text}", ""]

        lines += [
            "<sub>🤖 review-bot (Claude) | False Positive 의심 시 무시하세요</sub>",
        ]

        return "\n".join(lines)