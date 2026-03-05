"""
로컬 코드베이스 검색 도구.
Stage 2 에이전트가 로컬 레포의 소스 브랜치 코드를 읽어 레퍼런스 기반 검증을 수행한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from review_bot.agents.toolkit import ToolKit, ToolDefinition


class CodebaseSearcher:
    """로컬 코드베이스를 검색하는 도구 제공자."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def _safe_resolve(self, relative_path: str) -> Path | None:
        """Path traversal 방지: repo_root 밖으로 나가면 None 반환."""
        try:
            full = (self._root / relative_path).resolve()
            if not str(full).startswith(str(self._root)):
                return None
            return full
        except Exception:
            return None

    def search_code(self, pattern: str, file_glob: str = "", max_results: int = 20) -> str:
        """코드베이스에서 텍스트 패턴을 검색한다."""
        try:
            cmd = [
                "rg", "--line-number", "--max-count", str(max_results),
                "--no-heading", "--color", "never",
            ]
            if file_glob:
                cmd += ["--glob", file_glob]
            cmd += [pattern, str(self._root)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout[:5000]
        except FileNotFoundError:
            cmd = ["grep", "-rn"]
            if file_glob:
                cmd += ["--include", file_glob]
            cmd += [pattern, str(self._root)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = result.stdout[:5000]
        return output or "No matches found."

    def read_file_lines(self, file_path: str, start_line: int = 1, end_line: int | None = None) -> str:
        """특정 파일의 줄 범위를 읽는다."""
        full_path = self._safe_resolve(file_path)
        if full_path is None:
            return "Error: path traversal not allowed"
        if not full_path.is_file():
            return f"File not found: {file_path}"

        end = end_line or (start_line + 50)
        lines = full_path.read_text(errors="replace").splitlines()
        selected = lines[max(0, start_line - 1):end]
        numbered = [f"{i + start_line}: {line}" for i, line in enumerate(selected)]
        return "\n".join(numbered)[:4000]

    def list_directory(self, path: str = ".", recursive: bool = False) -> str:
        """디렉토리의 파일 목록을 조회한다."""
        dir_path = self._safe_resolve(path)
        if dir_path is None:
            return "Error: path traversal not allowed"
        if not dir_path.is_dir():
            return f"Not a directory: {path}"

        if recursive:
            files = [str(p.relative_to(self._root)) for p in dir_path.rglob("*") if p.is_file()]
        else:
            files = [str(p.relative_to(self._root)) for p in dir_path.iterdir()]
        return "\n".join(sorted(files)[:100]) or "Empty directory."

    def to_toolkit(self) -> ToolKit:
        """이 Searcher를 위한 ToolKit을 생성한다."""

        async def _search_code(args: dict) -> str:
            return self.search_code(
                args["pattern"], args.get("file_glob", ""), args.get("max_results", 20),
            )

        async def _read_file_lines(args: dict) -> str:
            return self.read_file_lines(
                args["file_path"], args.get("start_line", 1), args.get("end_line"),
            )

        async def _list_directory(args: dict) -> str:
            return self.list_directory(
                args.get("path", "."), args.get("recursive", False),
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
                        "file_glob": {"type": "string", "description": "File glob filter (e.g. '*.py'). Optional."},
                        "max_results": {"type": "integer", "description": "Max results (default 20)"},
                    },
                    "required": ["pattern"],
                },
                handler=_search_code,
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
                handler=_read_file_lines,
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
                handler=_list_directory,
            ),
        ])
