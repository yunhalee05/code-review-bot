"""프로바이더 무관 도구 정의."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class ToolDefinition:
    """단일 도구의 프로바이더 무관 정의.

    각 Runner가 이 정의를 자신의 SDK 형식(MCP tool, function_tool 등)으로 변환한다.
    """
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]


@dataclass
class ToolKit:
    """도구 정의를 담는 컨테이너."""
    tools: list[ToolDefinition] = field(default_factory=list)

    def merge(self, other: ToolKit) -> ToolKit:
        """두 ToolKit을 합친 새 ToolKit을 반환한다."""
        return ToolKit(tools=self.tools + other.tools)
