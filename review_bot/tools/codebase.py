"""
로컬 코드베이스 검색 도구.
Stage 2 에이전트가 레퍼런스 기반 검증 시 사용한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from review_bot.agents.toolkit import ToolKit, ToolDefinition


# ===========================================================================
# 공통 구현
# ===========================================================================

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
# ToolKit 팩토리
# ===========================================================================

def create_codebase_toolkit(repo_root: Path) -> ToolKit:
    """코드베이스 검색 도구 ToolKit을 생성한다."""
    resolved_root = repo_root.resolve()

    async def search_code(args: dict) -> str:
        return _search_code_impl(
            resolved_root, args["pattern"], args.get("file_glob", ""), args.get("max_results", 20),
        )

    async def read_file_lines(args: dict) -> str:
        return _read_file_lines_impl(
            resolved_root, args["file_path"], args.get("start_line", 1), args.get("end_line"),
        )

    async def list_directory(args: dict) -> str:
        return _list_directory_impl(
            resolved_root, args.get("path", "."), args.get("recursive", False),
        )

    return ToolKit(tools=[
        ToolDefinition(
            name="search_code",
            description=(
                "Search for a text pattern in the codebase. "
                "Returns matching lines with file paths and line numbers."
            ),
            schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
                    "file_glob": {"type": "string", "description": "File glob filter. Optional."},
                    "max_results": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": ["pattern"],
            },
            handler=search_code,
        ),
        ToolDefinition(
            name="read_file_lines",
            description="Read specific lines from a file in the repository.",
            schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative path from repo root"},
                    "start_line": {"type": "integer", "description": "Starting line (1-based). Default: 1"},
                    "end_line": {"type": "integer", "description": "Ending line (inclusive). Default: start+50"},
                },
                "required": ["file_path"],
            },
            handler=read_file_lines,
        ),
        ToolDefinition(
            name="list_directory",
            description="List files in a directory to understand project structure.",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (use '.' for root)"},
                    "recursive": {"type": "boolean", "description": "List recursively (default false)"},
                },
                "required": ["path"],
            },
            handler=list_directory,
        ),
    ])
