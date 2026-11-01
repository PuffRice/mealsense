"""Live terminal dashboard and final scraping report generator."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from tqdm import tqdm

from .metadata import ImageMetadata

logger = logging.getLogger(__name__)


def format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    total_secs = max(0, int(round(seconds)))
    hours, remainder = divmod(total_secs, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_size(size_bytes: int) -> str:
    """Format byte count in human-readable MB or GB."""
    size_mb = size_bytes / (1024 * 1024)
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB ({size_mb:.2f} MB)"
    return f"{size_mb:.2f} MB"


@dataclass
class ScrapingStats:
    """Tracks live metrics and final statistics for a scraping session."""

    group_url: str
    group_id: str
    target_images: int
    start_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completion_timestamp: Optional[str] = None
    start_monotonic: float = field(default_factory=time.perf_counter)
    posts_inspected: int = 0
    current_post_id: str = "None"
    images_discovered: int = 0
    images_downloaded: int = 0
    resumed_images_count: int = 0
    failed_downloads: int = 0
    duplicate_images: int = 0
    total_bytes_downloaded: int = 0
    active_download_seconds: float = 0.0
    last_speed_kbps: float = 0.0
    termination_reason: str = "Completed"

    @property
    def elapsed_seconds(self) -> float:
        """Wall-clock elapsed seconds since session start."""
        return max(0.0, time.perf_counter() - self.start_monotonic)

    @property
    def estimated_remaining_seconds(self) -> Optional[float]:
        """Estimate remaining time based on current download rate."""
        new_downloads = max(0, self.images_downloaded - self.resumed_images_count)
        remaining_items = max(0, self.target_images - self.images_downloaded)
        if remaining_items == 0:
            return 0.0
        if new_downloads <= 0 or self.elapsed_seconds <= 0:
            return None
        rate_per_sec = new_downloads / self.elapsed_seconds
        return remaining_items / rate_per_sec

    @property
    def average_speed_kbps(self) -> float:
        """Average download speed in KB/s across all active downloads."""
        if self.active_download_seconds <= 0:
            return 0.0
        return (self.total_bytes_downloaded / 1024.0) / self.active_download_seconds


class ProgressDashboard:
    """Displays a live terminal dashboard using Rich (with tqdm progress tracking)."""

    def __init__(self, stats: ScrapingStats, enabled: bool = True) -> None:
        self.stats = stats
        self.enabled = enabled
        self.console = Console()
        self._live: Optional[Live] = None
        self._tqdm_bar: Optional[tqdm] = None

    def __enter__(self) -> ProgressDashboard:
        if self.enabled:
            self._live = Live(
                self.render_panel(),
                console=self.console,
                refresh_per_second=4,
                transient=False,
            )
            self._live.__enter__()
        else:
            self._tqdm_bar = tqdm(
                total=self.stats.target_images,
                initial=self.stats.images_downloaded,
                desc=f"Group {self.stats.group_id}",
                unit="img",
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._live is not None:
            self._live.update(self.render_panel())
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None
        if self._tqdm_bar is not None:
            self._tqdm_bar.close()
            self._tqdm_bar = None

    def update(self) -> None:
        """Refresh the live terminal display."""
        if self._live is not None:
            self._live.update(self.render_panel())
        elif self._tqdm_bar is not None:
            self._tqdm_bar.n = self.stats.images_downloaded
            self._tqdm_bar.set_postfix(
                disc=self.stats.images_discovered,
                fail=self.stats.failed_downloads,
                dup=self.stats.duplicate_images,
                posts=self.stats.posts_inspected,
            )
            self._tqdm_bar.refresh()

    def render_text_summary(self) -> str:
        """Render the exact plain-text dashboard representation."""
        eta = self.stats.estimated_remaining_seconds
        eta_str = format_duration(eta) if eta is not None else "Calculating..."
        speed_str = f"{self.stats.last_speed_kbps:.1f} KB/s (avg {self.stats.average_speed_kbps:.1f} KB/s)"
        lines = [
            "Facebook Group Image Scraper",
            "------------------------------------",
            f"Group: {self.stats.group_id}",
            f"Target images: {self.stats.target_images}",
            f"Discovered: {self.stats.images_discovered}",
            f"Downloaded: {self.stats.images_downloaded}",
            f"Failed: {self.stats.failed_downloads}",
            f"Duplicates: {self.stats.duplicate_images}",
            f"Posts inspected: {self.stats.posts_inspected}",
            f"Current post: {self.stats.current_post_id}",
            f"Download speed: {speed_str}",
            "",
            f"Progress: {self.stats.images_downloaded} / {self.stats.target_images}",
            f"Elapsed: {format_duration(self.stats.elapsed_seconds)}",
            f"Estimated remaining: {eta_str}",
            "------------------------------------",
        ]
        return "\n".join(lines)

    def render_panel(self) -> Panel:
        """Render a Rich Panel containing the live dashboard metrics."""
        eta = self.stats.estimated_remaining_seconds
        eta_str = format_duration(eta) if eta is not None else "Calculating..."
        pct = (
            min(100.0, (self.stats.images_downloaded / self.stats.target_images) * 100.0)
            if self.stats.target_images > 0
            else 0.0
        )

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", justify="left")
        table.add_column(style="white", justify="left")

        table.add_row("Group:", f"{self.stats.group_id} ({self.stats.group_url})")
        table.add_row("Target images:", str(self.stats.target_images))
        table.add_row("Discovered:", str(self.stats.images_discovered))
        table.add_row("Downloaded:", f"[bold green]{self.stats.images_downloaded}[/bold green]")
        table.add_row("Failed:", f"[bold red]{self.stats.failed_downloads}[/bold red]")
        table.add_row("Duplicates:", f"[yellow]{self.stats.duplicate_images}[/yellow]")
        table.add_row("Posts inspected:", str(self.stats.posts_inspected))
        table.add_row("Current post:", str(self.stats.current_post_id))
        table.add_row(
            "Download speed:",
            f"{self.stats.last_speed_kbps:.1f} KB/s (avg {self.stats.average_speed_kbps:.1f} KB/s)",
        )
        table.add_row("", "")
        table.add_row(
            "Progress:",
            f"[bold]{self.stats.images_downloaded} / {self.stats.target_images}[/bold] ({pct:.1f}%)",
        )
        table.add_row("Elapsed:", format_duration(self.stats.elapsed_seconds))
        table.add_row("Estimated remaining:", eta_str)

        return Panel(
            table,
            title="[bold white]Facebook Group Image Scraper[/bold white]",
            border_style="bright_blue",
            expand=False,
        )


def generate_final_report(
    stats: ScrapingStats,
    records: List[ImageMetadata],
    report_path: Path,
) -> Dict[str, object]:
    """Compute final dataset statistics, write `scraping_report.json`, and return the report dict."""
    if not stats.completion_timestamp:
        stats.completion_timestamp = datetime.now(timezone.utc).isoformat()

    total_dataset_bytes = sum(r.file_size_bytes for r in records)
    total_dataset_mb = round(total_dataset_bytes / (1024 * 1024), 4)
    total_dataset_gb = round(total_dataset_bytes / (1024 * 1024 * 1024), 6)

    if records:
        avg_width = round(sum(r.width for r in records) / len(records), 1)
        avg_height = round(sum(r.height for r in records) / len(records), 1)
        avg_dimensions_str = f"{avg_width} x {avg_height} px"
    else:
        avg_width = 0.0
        avg_height = 0.0
        avg_dimensions_str = "0 x 0 px"

    duration_seconds = round(stats.elapsed_seconds, 2)
    report: Dict[str, object] = {
        "group_url": stats.group_url,
        "group_id": stats.group_id,
        "start_timestamp": stats.start_timestamp,
        "completion_timestamp": stats.completion_timestamp,
        "termination_reason": stats.termination_reason,
        "total_posts_inspected": stats.posts_inspected,
        "total_image_urls_discovered": stats.images_discovered,
        "total_images_downloaded": len(records),
        "session_new_images_downloaded": max(0, len(records) - stats.resumed_images_count),
        "resumed_images_from_previous_session": stats.resumed_images_count,
        "failed_downloads": stats.failed_downloads,
        "duplicate_images": stats.duplicate_images,
        "total_dataset_size_bytes": total_dataset_bytes,
        "total_dataset_size_mb": total_dataset_mb,
        "total_dataset_size_gb": total_dataset_gb,
        "total_dataset_size_formatted": format_size(total_dataset_bytes),
        "average_image_width": avg_width,
        "average_image_height": avg_height,
        "average_image_dimensions": avg_dimensions_str,
        "average_download_speed_kbps": round(stats.average_speed_kbps, 2),
        "total_scraping_duration_seconds": duration_seconds,
        "total_scraping_duration_formatted": format_duration(duration_seconds),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Final scraping report written to %s", report_path)
    return report


def format_report_summary(report: Dict[str, object]) -> str:
    """Format the final scraping report for terminal output."""
    lines = [
        "",
        "=" * 68,
        "                    FINAL SCRAPING REPORT",
        "=" * 68,
        f"  Group URL                  : {report['group_url']}",
        f"  Resolved Group ID          : {report['group_id']}",
        f"  Status / Reason            : {report['termination_reason']}",
        f"  Start Timestamp (UTC)      : {report['start_timestamp']}",
        f"  Completion Timestamp (UTC) : {report['completion_timestamp']}",
        "-" * 68,
        f"  Total Posts Inspected      : {report['total_posts_inspected']}",
        f"  Total Image URLs Discovered: {report['total_image_urls_discovered']}",
        f"  Total Images in Dataset    : {report['total_images_downloaded']} "
        f"(New: {report['session_new_images_downloaded']}, Resumed: {report['resumed_images_from_previous_session']})",
        f"  Failed Downloads           : {report['failed_downloads']}",
        f"  Duplicate Images Skipped   : {report['duplicate_images']}",
        "-" * 68,
        f"  Total Dataset Size         : {report['total_dataset_size_formatted']}",
        f"  Average Image Dimensions   : {report['average_image_dimensions']}",
        f"  Average Download Speed     : {report['average_download_speed_kbps']} KB/s",
        f"  Total Scraping Duration    : {report['total_scraping_duration_formatted']} "
        f"({report['total_scraping_duration_seconds']}s)",
        "=" * 68,
    ]
    return "\n".join(lines)
