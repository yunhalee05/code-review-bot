"""
로컬 코드베이스 검색 도구.
Stage 2 에이전트가 레퍼런스 기반 검증 시 사용한다.

Claude Agent SDK와 OpenAI Agents SDK 양쪽 모두 지원한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _safe_resolve(resolved_root: Path, relative_path: str) -> Path | None:
    """Path traversal 방지: repo_root 밖으로 나가면 None 반환."""
    try:
        full = (resolved_root / relative_path).resolve()
        if not str(full).startswith(str(resolved_root)):
            return None
        return full
    except Exception:
        return None


def _search_code_impl(
    resolved_root: Path, pattern: str, file_glob: str = "", max_results: int = 20,
) -> str:
    """코드베이스에서 패턴을 검색하는 공통 구현."""
    try:
        cmd = [
            "rg", "--line-number", "--max-count", str(max_results),
            "--no-heading", "--color", "never",
        ]
        if file_glob:
            cmd += ["--glob", file_glob]
        cmd += [pattern, str(resolved_root)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = result.stdout[:5000]
    except FileNotFoundError:
        cmd = ["grep", "-rn"]
        if file_glob:
            cmd += ["--include", file_glob]
        cmd += [pattern, str(resolved_root)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = result.stdout[:5000]
    return output or "No matches found."


def _read_file_lines_impl(
    resolved_root: Path, file_path: str, start_line: int = 1, end_line: int | None = None,
) -> str:
    """파일의 특정 줄을 읽는 공통 구현."""
    full_path = _safe_resolve(resolved_root, file_path)
    if full_path is None:
        return "Error: path traversal not allowed"
    if not full_path.is_file():
        return f"File not found: {file_path}"

    end = end_line or (start_line + 50)
    lines = full_path.read_text(errors="replace").splitlines()
    selected = lines[max(0, start_line - 1):end]
    numbered = [f"{i + start_line}: {line}" for i, line in enumerate(selected)]
    return "\n".join(numbered)[:4000]


def _list_directory_impl(
    resolved_root: Path, path: str = ".", recursive: bool = False,
) -> str:
    """디렉토리 목록을 반환하는 공통 구현."""
    dir_path = _safe_resolve(resolved_root, path)
    if dir_path is None:
        return "Error: path traversal not allowed"
    if not dir_path.is_dir():
        return f"Not a directory: {path}"

    if recursive:
        files = [str(p.relative_to(resolved_root)) for p in dir_path.rglob("*") if p.is_file()]
    else:
        files = [str(p.relative_to(resolved_root)) for p in dir_path.iterdir()]
    return "\n".join(sorted(files)[:100]) or "Empty directory."


# ===========================================================================
# Claude Agent SDK — MCP 서버 팩토리
# ===========================================================================

def create_codebase_server(repo_root: Path):
    """로컬 레포를 대상으로 검색/읽기/탐색 도구를 제공하는 Claude MCP 서버 생성."""
    from claude_agent_sdk import tool, create_sdk_mcp_server

    resolved_root = repo_root.resolve()

    @tool(
        "search_code",
        "Search for a text pattern in the codebase. "
        "Returns matching lines with file paths and line numbers.",
        {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for",
                },
                "file_glob": {
                    "type": "string",
                    "description": "File glob filter (e.g. '*.py', '*.java'). Optional.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default 20)",
                },
            },
            "required": ["pattern"],
        },
    )
    async def search_code(args: dict[str, Any]) -> dict[str, Any]:
        output = _search_code_impl(
            resolved_root,
            args["pattern"],
            args.get("file_glob", ""),
            args.get("max_results", 20),
        )
        return {"content": [{"type": "text", "text": output}]}

    @tool(
        "read_file_lines",
        "Read specific lines from a file in the repository.",
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path from repo root",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Starting line number (1-based). Default: 1",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Ending line number (inclusive). Default: start_line + 50",
                },
            },
            "required": ["file_path"],
        },
    )
    async def read_file_lines(args: dict[str, Any]) -> dict[str, Any]:
        output = _read_file_lines_impl(
            resolved_root,
            args["file_path"],
            args.get("start_line", 1),
            args.get("end_line"),
        )
        return {"content": [{"type": "text", "text": output}]}

    @tool(
        "list_directory",
        "List files in a directory to understand project structure.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path from repo root (use '.' for root)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "If true, list recursively (default false)",
                },
            },
            "required": ["path"],
        },
    )
    async def list_directory(args: dict[str, Any]) -> dict[str, Any]:
        output = _list_directory_impl(
            resolved_root,
            args.get("path", "."),
            args.get("recursive", False),
        )
        return {"content": [{"type": "text", "text": output}]}

    return create_sdk_mcp_server(
        name="codebase",
        version="1.0.0",
        tools=[search_code, read_file_lines, list_directory],
    )


# ===========================================================================
# OpenAI Agents SDK — function_tool 팩토리
# ===========================================================================

def create_codebase_openai_tools(repo_root: Path) -> list:
    """로컬 레포를 대상으로 검색/읽기/탐색 OpenAI function_tool 리스트 생성."""
    from agents import function_tool

    resolved_root = repo_root.resolve()

    @function_tool
    async def search_code(
        pattern: str,
        file_glob: str = "",
        max_results: int = 20,
    ) -> str:
        """코드베이스에서 텍스트 패턴을 검색합니다. 파일 경로와 줄 번호가 포함된 결과를 반환합니다.

        Args:
            pattern: 검색할 텍스트 또는 정규식 패턴
            file_glob: 파일 글로브 필터 (예: '*.py', '*.java'). 선택사항.
            max_results: 반환할 최대 결과 수 (기본: 20)
        """
        return _search_code_impl(resolved_root, pattern, file_glob, max_results)

    @function_tool
    async def read_file_lines(
        file_path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        """레포지토리 내 파일의 특정 줄을 읽습니다.

        Args:
            file_path: 레포 루트 기준 상대 경로
            start_line: 시작 줄 번호 (1부터). 기본: 1
            end_line: 끝 줄 번호 (포함). 기본: start_line + 50
        """
        return _read_file_lines_impl(resolved_root, file_path, start_line, end_line)

    @function_tool
    async def list_directory(
        path: str = ".",
        recursive: bool = False,
    ) -> str:
        """디렉토리의 파일 목록을 조회하여 프로젝트 구조를 파악합니다.

        Args:
            path: 레포 루트 기준 상대 디렉토리 경로 (루트는 '.')
            recursive: True면 하위 디렉토리까지 재귀 조회 (기본: False)
        """
        return _list_directory_impl(resolved_root, path, recursive)

    return [search_code, read_file_lines, list_directory]
