"""
StorageTool 패턴: Tool Call을 데이터 전송 레이어로 활용.
에이전트가 tool call을 통해 구조화된 데이터를 제출하면, storage 객체에 수집된다.

Claude Agent SDK와 OpenAI Agents SDK 양쪽 모두 지원한다.
"""

from __future__ import annotations

from typing import Any

from review_bot.models.issue import Issue, ValidatedIssue, Severity


# ===========================================================================
# 프로바이더 무관 Storage 클래스
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
# Claude Agent SDK — MCP 서버 팩토리
# ===========================================================================

def create_issue_storage_server(storage: IssueStorage):
    """IssueStorage에 바인딩된 Claude MCP 서버 생성."""
    from claude_agent_sdk import tool, create_sdk_mcp_server

    @tool(
        "report_issue",
        "Report a code review issue found in the diff hunk. "
        "Call this once for each distinct issue you find.",
        {
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
    )
    async def report_issue(args: dict[str, Any]) -> dict[str, Any]:
        result = storage.add(
            code=args["code"],
            title=args["title"],
            description=args["description"],
            severity=args["severity"],
            line_number=args["line_number"],
        )
        return {"content": [{"type": "text", "text": result}]}

    return create_sdk_mcp_server(
        name="issue_storage",
        version="1.0.0",
        tools=[report_issue],
    )


def create_validation_storage_server(storage: ValidationStorage):
    """ValidationStorage에 바인딩된 Claude MCP 서버 생성."""
    from claude_agent_sdk import tool, create_sdk_mcp_server

    @tool(
        "submit_validated_issue",
        "Submit your validation result for the issue. "
        "Call this exactly once after collecting evidence from the codebase.",
        {
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
    )
    async def submit_validated_issue(args: dict[str, Any]) -> dict[str, Any]:
        result = storage.submit(
            is_false_positive=args["is_false_positive"],
            evidence=args["evidence"],
            mitigation=args["mitigation"],
            suggestion=args["suggestion"],
            references=args.get("references", []),
        )
        return {"content": [{"type": "text", "text": result}]}

    return create_sdk_mcp_server(
        name="validation",
        version="1.0.0",
        tools=[submit_validated_issue],
    )


# ===========================================================================
# OpenAI Agents SDK — function_tool 팩토리
# ===========================================================================

def create_issue_openai_tools(storage: IssueStorage) -> list:
    """IssueStorage에 바인딩된 OpenAI function_tool 리스트 생성."""
    from agents import function_tool

    @function_tool
    async def report_issue(
        code: str,
        title: str,
        description: str,
        severity: str,
        line_number: int,
    ) -> str:
        """코드 리뷰에서 발견한 이슈를 보고합니다. 각 이슈마다 한 번씩 호출하세요.

        Args:
            code: 이슈 식별 코드 (예: SEC001, BUG002, TXN001, PERF003)
            title: 이슈 한 줄 요약
            description: 왜 이것이 문제인지 상세 설명
            severity: 심각도 (critical, high, medium, low)
            line_number: 이슈가 있는 새 파일의 줄 번호
        """
        return storage.add(code, title, description, severity, line_number)

    return [report_issue]


def create_validation_openai_tools(storage: ValidationStorage) -> list:
    """ValidationStorage에 바인딩된 OpenAI function_tool 리스트 생성."""
    from agents import function_tool

    @function_tool
    async def submit_validated_issue(
        is_false_positive: bool,
        evidence: str,
        mitigation: str,
        suggestion: str,
        references: list[str] | None = None,
    ) -> str:
        """이슈 검증 결과를 제출합니다. 근거를 수집한 후 정확히 한 번만 호출하세요.

        Args:
            is_false_positive: 오탐이면 True
            evidence: 실제 문제임을 뒷받침하는 근거
            mitigation: 오탐일 수 있는 근거
            suggestion: 수정 제안 코드 또는 방법 (실제 이슈인 경우)
            references: 참조한 파일 경로 또는 코드 위치
        """
        return storage.submit(
            is_false_positive=is_false_positive,
            evidence=evidence,
            mitigation=mitigation,
            suggestion=suggestion,
            references=references,
        )

    return [submit_validated_issue]
