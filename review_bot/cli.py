"""
CLI 엔트리포인트.
review-bot review <MR_ID> 명령으로 리뷰를 실행한다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from review_bot.models.issue import Severity

app = typer.Typer(
    name="review-bot",
    help="Local Multi-Agent Code Review Bot for GitLab MR",
    add_completion=False,
)
console = Console()


@app.command()
def review(
    mr_id: int = typer.Argument(..., help="GitLab Merge Request ID"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Analyze without posting comments to GitLab",
    ),
    severity: str = typer.Option(
        "medium", "--severity", "-s",
        help="Minimum severity to report: critical/high/medium/low",
    ),
    concurrency: int = typer.Option(
        4, "--concurrency", "-c",
        help="Max parallel agent invocations",
    ),
    repo_root: Path = typer.Option(
        ".", "--repo-root", "-r",
        help="Local repository root path (source branch checkout)",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Show detailed agent output",
    ),
) -> None:
    """Review a GitLab MR and post AI-generated review comments."""
    # 로깅 설정
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # severity 파싱
    try:
        severity_threshold = Severity(severity.lower())
    except ValueError:
        console.print(f"[red]Invalid severity: {severity}[/red]")
        console.print("Valid values: critical, high, medium, low")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Review Bot[/bold] - MR !{mr_id}")
    if dry_run:
        console.print("[yellow]Dry-run mode: comments will NOT be posted[/yellow]")
    console.print(f"Severity threshold: {severity_threshold.value}")
    console.print(f"Repo root: {repo_root.resolve()}")
    console.print()

    # 파이프라인 실행
    from review_bot.pipeline import run_review

    try:
        result = asyncio.run(
            run_review(
                mr_id=mr_id,
                repo_root=repo_root.resolve(),
                dry_run=dry_run,
                severity_threshold=severity_threshold,
                max_concurrent=concurrency,
            )
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)

    # 결과 출력
    console.print(f"\n[bold]MR:[/bold] {result.mr_info.title}")
    console.print(f"[bold]URL:[/bold] {result.mr_info.url}")
    console.print(f"[bold]Author:[/bold] {result.mr_info.author}")
    console.print()

    console.print(f"Hunks analyzed: {result.total_hunks}")
    console.print(f"Issues found (Stage 1): {result.total_issues_found}")
    console.print(f"False positives (Stage 2): {result.false_positives}")
    console.print(f"[bold green]Issues posted: {result.issues_posted}[/bold green]")

    if result.issues:
        console.print()
        table = Table(title="Review Issues")
        table.add_column("#", style="dim", width=4)
        table.add_column("Severity", width=10)
        table.add_column("Code", width=10)
        table.add_column("File", width=30)
        table.add_column("Title")

        severity_style = {
            Severity.CRITICAL: "bold red",
            Severity.HIGH: "red",
            Severity.MEDIUM: "yellow",
            Severity.LOW: "blue",
        }

        for i, issue in enumerate(result.issues, 1):
            style = severity_style.get(issue.severity, "")
            table.add_row(
                str(i),
                f"[{style}]{issue.severity.value.upper()}[/{style}]",
                issue.issue.code,
                f"{issue.file_path}:{issue.line_number}",
                issue.issue.title,
            )

        console.print(table)


@app.command()
def check_config() -> None:
    """Verify configuration and connectivity."""
    from review_bot.config import settings

    console.print("[bold]Configuration Check[/bold]\n")

    # GitLab
    console.print(f"GitLab URL: {settings.gitlab_url}")
    console.print(f"GitLab Project ID: {settings.gitlab_project_id}")
    console.print(f"GitLab Token: {'*' * 8}...{settings.gitlab_token[-4:]}")

    try:
        from review_bot.gitlab.client import GitLabClient
        client = GitLabClient()
        console.print("[green]GitLab connection: OK[/green]")
    except Exception as e:
        console.print(f"[red]GitLab connection: FAILED - {e}[/red]")

    # Anthropic
    console.print(f"\nAnthropic API Key: {'*' * 8}...{settings.anthropic_api_key[-4:]}")
    console.print(f"Review Model: {settings.review_model}")

    # Settings
    console.print(f"\nMax files per MR: {settings.max_files_per_mr}")
    console.print(f"Max hunks per file: {settings.max_hunks_per_file}")


if __name__ == "__main__":
    app()
