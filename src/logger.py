"""ログ管理モジュール - 構造化ログとプログレス表示"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.logging import RichHandler

from .config import LOGS_DIR, config

console = Console()


def setup_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """構造化ロガーをセットアップ"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.log_level))

    if logger.handlers:
        return logger

    # リッチハンドラー（コンソール出力）
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
    )
    rich_handler.setLevel(logging.INFO)
    logger.addHandler(rich_handler)

    # ファイルハンドラー
    if log_file is None:
        log_file = LOGS_DIR / f"{name}_{datetime.now():%Y%m%d}.log"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    ))
    logger.addHandler(file_handler)

    return logger


class ProgressManager:
    """プログレスバー管理クラス"""

    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        )
        self._tasks = {}

    def __enter__(self):
        self.progress.__enter__()
        return self

    def __exit__(self, *args):
        self.progress.__exit__(*args)

    def add_task(self, description: str, total: int = 100) -> int:
        """タスクを追加"""
        task_id = self.progress.add_task(description, total=total)
        self._tasks[description] = task_id
        return task_id

    def update(self, task_id: int, advance: int = 1, description: str = None):
        """進捗を更新"""
        if description:
            self.progress.update(task_id, description=description)
        self.progress.update(task_id, advance=advance)

    def complete(self, task_id: int, description: str = None):
        """タスクを完了"""
        task = self.progress.tasks[task_id]
        remaining = task.total - task.completed
        if description:
            self.progress.update(task_id, description=description)
        self.progress.update(task_id, advance=remaining)


def print_header(title: str):
    """ヘッダー表示"""
    console.print(f"\n[bold cyan]{'=' * 50}[/bold cyan]")
    console.print(f"[bold white]{title}[/bold white]")
    console.print(f"[bold cyan]{'=' * 50}[/bold cyan]\n")


def print_success(message: str):
    """成功メッセージ"""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str):
    """エラーメッセージ"""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str):
    """警告メッセージ"""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str):
    """情報メッセージ"""
    console.print(f"[blue]i[/blue] {message}")


# デフォルトロガー
logger = setup_logger("ai_video")
