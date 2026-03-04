
from dataclasses import dataclass, field


@dataclass
class Hunk:
    """Git diff의 hunk 단위 변경 블록"""

    file_path: str
    old_path: str  # 파일명 변경 시 이전 경로
    new_start_line: int
    new_line_count: int
    content: str  # hunk 원문 (+/-/공백 포함)
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    file_extension: str = ""

    def __post_init__(self):
        self.file_extension = self.file_path.rsplit(".", 1)[-1] if "." in self.file_path else ""

    @property
    def summary(self) -> str:
        return (
            f"{self.file_path} "
            f"(+{len(self.added_lines)}/-{len(self.removed_lines)}) "
            f"@ line {self.new_start_line}"
        )
