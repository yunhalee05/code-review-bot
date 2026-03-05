"""
StorageTool 패턴: Tool Call을 데이터 전송 레이어로 활용.
에이전트가 tool call을 통해 구조화된 데이터를 제출하면, storage 객체에 수집된다.
"""

from __future__ import annotations

from review_bot.agents.toolkit import ToolKit, ToolDefinition
from review_bot.models.issue import Issue, ValidatedIssue, Severity


# ===========================================================================
# Storage 클래스
# ===========================================================================

class IssueStorage:
    """Stage 1 에이전트가 발견한 이슈를 수집하는 컨테이너."""

    def __init__(self, file_path: str) -> None:
        self.issues: list[Issue] = []
        self.file_path = file_path

    def add(
        self,
        code: str,
        title: str,
        description: str,
        severity: str,
        line_number: int,
    ) -> str:
        issue = Issue(
            file_path=self.file_path,
            line_number=line_number,
            code=code,
            title=title,
            description=description,
            severity=Severity(severity),
        )
        self.issues.append(issue)
        return f"Issue {code} recorded."


class ValidationStorage:
    """Stage 2 에이전트가 검증 결과를 제출하는 컨테이너."""

    def __init__(self, issue: Issue) -> None:
        self.issue = issue
        self.result: ValidatedIssue | None = None

    def submit(
        self,
        is_false_positive: bool,
        evidence: str,
        mitigation: str,
        suggestion: str,
        references: list[str] | None = None,
    ) -> str:
        self.result = ValidatedIssue(
            issue=self.issue,
            is_false_positive=is_false_positive,
            evidence=evidence,
            mitigation=mitigation,
            suggestion=suggestion,
            references=references or [],
        )
        return "Validation result recorded."


# ===========================================================================
# ToolKit 팩토리
# ===========================================================================

def create_issue_toolkit(storage: IssueStorage) -> ToolKit:
    """IssueStorage 기반 ToolKit을 생성한다."""

    async def report_issue(args: dict) -> str:
        return storage.add(
            code=args["code"],
            title=args["title"],
            description=args["description"],
            severity=args["severity"],
            line_number=args["line_number"],
        )

    return ToolKit(tools=[
        ToolDefinition(
            name="report_issue",
            description=(
                "Report a code review issue found in the diff hunk. "
                "Call this once for each distinct issue you find."
            ),
            schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Issue identifier (e.g. SEC001, BUG002, TXN001, PERF003)",
                    },
                    "title": {
                        "type": "string",
                        "description": "One-line summary of the issue",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed explanation of why this is a problem",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Issue severity level",
                    },
                    "line_number": {
                        "type": "integer",
                        "description": "Line number in the new file where the issue is",
                    },
                },
                "required": ["code", "title", "description", "severity", "line_number"],
            },
            handler=report_issue,
        ),
    ])


def create_validation_toolkit(storage: ValidationStorage) -> ToolKit:
    """ValidationStorage 기반 ToolKit을 생성한다."""

    async def submit_validated_issue(args: dict) -> str:
        return storage.submit(
            is_false_positive=args["is_false_positive"],
            evidence=args["evidence"],
            mitigation=args["mitigation"],
            suggestion=args["suggestion"],
            references=args.get("references", []),
        )

    return ToolKit(tools=[
        ToolDefinition(
            name="submit_validated_issue",
            description=(
                "Submit your validation result for the issue. "
                "Call this exactly once after collecting evidence from the codebase."
            ),
            schema={
                "type": "object",
                "properties": {
                    "is_false_positive": {
                        "type": "boolean",
                        "description": "True if this issue is a false positive",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Evidence supporting this as a real issue",
                    },
                    "mitigation": {
                        "type": "string",
                        "description": "Evidence suggesting this might be a false positive",
                    },
                    "suggestion": {
                        "type": "string",
                        "description": "Suggested code fix or approach (if real issue)",
                    },
                    "references": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Referenced file paths or code locations",
                    },
                },
                "required": ["is_false_positive", "evidence", "mitigation", "suggestion"],
            },
            handler=submit_validated_issue,
        ),
    ])
