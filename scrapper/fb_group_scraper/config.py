"""Configuration models and interactive CLI prompts for the Facebook Group Image Scraper."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ScraperConfig:
    """Holds all user-configurable parameters for a scraping session.

    Note on timing parameters:
    `facebook-scraper` is an HTTP-based HTML parser targeting m.facebook.com, NOT a
    browser automation framework (like Selenium or Playwright). Therefore, `post_delay`
    (configured at the prompt as the gallery/page loading wait time) does NOT wait for
    client-side JavaScript or dynamic DOM rendering of a gallery grid. Instead, it acts
    as a polite rate-limiting delay (in seconds) between HTTP requests / post inspections
    to prevent triggering Facebook's automated anti-scraping rate limits.
    """

    group_url: str
    group_id: str = ""
    max_images: int = 100
    post_delay: float = 2.0
    download_delay: float = 1.0
    max_posts: int = 200
    output_dir: Path = Path("facebook_group_dataset")
    include_multi_image_albums: bool = True
    request_timeout: int = 30
    max_retries: int = 3
    backoff_factor: float = 2.0
    resume: bool = True
    filter_food_only: bool = True
    food_confidence_threshold: float = 0.50

    @property
    def images_dir(self) -> Path:
        """Directory where downloaded image files are stored."""
        return self.output_dir / "images"

    @property
    def food_images_dir(self) -> Path:
        """Directory where verified food-only images are moved."""
        return self.output_dir / "food_images"

    @property
    def non_food_images_dir(self) -> Path:
        """Directory where non-food images are separated."""
        return self.output_dir / "non_food_images"

    @property
    def metadata_dir(self) -> Path:
        """Directory where CSV/JSON metadata and final reports are stored."""
        return self.output_dir / "metadata"

    @property
    def logs_dir(self) -> Path:
        """Directory where runtime log files are stored."""
        return self.output_dir / "logs"

    @property
    def metadata_csv_path(self) -> Path:
        """Path to the incremental CSV metadata file."""
        return self.metadata_dir / "images_metadata.csv"

    @property
    def metadata_json_path(self) -> Path:
        """Path to the incremental JSON metadata file."""
        return self.metadata_dir / "images_metadata.json"

    @property
    def report_json_path(self) -> Path:
        """Path to the final scraping summary report JSON file."""
        return self.metadata_dir / "scraping_report.json"

    @property
    def log_file_path(self) -> Path:
        """Path to the application log file."""
        return self.logs_dir / "scraper.log"


def _prompt_with_default(prompt_text: str, default: str) -> str:
    """Prompt the user for input, returning `default` when Enter is pressed."""
    try:
        raw = input(f"{prompt_text} [{default}]: ").strip()
    except EOFError:
        return default
    return raw if raw else default


def _prompt_int(prompt_text: str, default: int, min_val: int = 1) -> int:
    """Prompt for a positive integer with validation and a default value."""
    while True:
        val_str = _prompt_with_default(prompt_text, str(default))
        try:
            val = int(val_str)
            if val < min_val:
                print(f"  [!] Value must be at least {min_val}. Please try again.")
                continue
            return val
        except ValueError:
            print("  [!] Invalid integer. Please enter a whole number.")


def _prompt_float(prompt_text: str, default: float, min_val: float = 0.0) -> float:
    """Prompt for a non-negative float with validation and a default value."""
    while True:
        val_str = _prompt_with_default(prompt_text, str(default))
        try:
            val = float(val_str)
            if val < min_val:
                print(f"  [!] Value must be at least {min_val}. Please try again.")
                continue
            return val
        except ValueError:
            print("  [!] Invalid number. Please enter a numeric value (e.g. 1.5).")


def _prompt_bool(prompt_text: str, default: bool = True) -> bool:
    """Prompt for a Yes/No boolean choice with a default value."""
    default_hint = "Y/n" if default else "y/N"
    while True:
        try:
            raw = input(f"{prompt_text} [{default_hint}]: ").strip().lower()
        except EOFError:
            return default
        if not raw:
            return default
        if raw in ("y", "yes", "true", "1"):
            return True
        if raw in ("n", "no", "false", "0"):
            return False
        print("  [!] Please enter 'y' (yes) or 'n' (no).")


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser supporting both CLI flags and interactive mode."""
    parser = argparse.ArgumentParser(
        prog="fb-group-image-scraper",
        description=(
            "Configurable Facebook Group Gallery Image Scraper built on facebook-scraper.\n"
            "Note: facebook-scraper extracts group posts via m.facebook.com rather than "
            "rendering JavaScript gallery grids. Group Gallery URLs are resolved to their "
            "parent group identifier and scraped via get_posts(group=...)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        "-u",
        type=str,
        default=None,
        help="Facebook Group Gallery URL (e.g., https://www.facebook.com/groups/example/media)",
    )
    parser.add_argument(
        "--max-images",
        "-n",
        type=int,
        default=100,
        help="Maximum number of images to download (default: 100)",
    )
    parser.add_argument(
        "--post-delay",
        type=float,
        default=2.0,
        help=(
            "Post retrieval / gallery page wait time in seconds (default: 2.0). "
            "Acts as a polite rate-limiting delay between post fetches."
        ),
    )
    parser.add_argument(
        "--download-delay",
        type=float,
        default=1.0,
        help="Delay between individual image downloads in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--max-posts",
        "-p",
        type=int,
        default=200,
        help="Maximum number of group posts to inspect (default: 200)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="facebook_group_dataset",
        help="Output dataset directory (default: facebook_group_dataset)",
    )
    parser.add_argument(
        "--include-albums",
        dest="include_albums",
        action="store_true",
        default=True,
        help="Include gallery albums / posts containing multiple images (default: True)",
    )
    parser.add_argument(
        "--single-image-only",
        dest="include_albums",
        action="store_false",
        help="Only extract the primary image per post and skip multi-image albums",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries for transient HTTP errors with exponential backoff (default: 3)",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Disable resuming from existing metadata in the output directory",
    )
    parser.add_argument(
        "--filter-food",
        dest="filter_food",
        action="store_true",
        default=True,
        help="Filter downloaded images with a vision model and move food images to food_images/ (default: True)",
    )
    parser.add_argument(
        "--no-filter-food",
        dest="filter_food",
        action="store_false",
        help="Disable automatic food image classification and moving",
    )
    parser.add_argument(
        "--filter-only",
        action="store_true",
        default=False,
        help="Only run the vision food filter on already-downloaded images in --output-dir without scraping",
    )
    parser.add_argument(
        "--food-threshold",
        type=float,
        default=0.50,
        help="Confidence threshold (0.0-1.0) for classifying an image as food (default: 0.50)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        default=False,
        help="Run without interactive prompts (requires --url)",
    )
    return parser


def prompt_interactive_config(defaults: Optional[argparse.Namespace] = None) -> ScraperConfig:
    """Run the interactive CLI configuration wizard with sensible defaults."""
    print("=" * 72)
    print("  Facebook Group Gallery Image Scraper - Interactive Configuration")
    print("=" * 72)
    print(
        "\n[Technical Note on facebook-scraper & Timing Parameters]\n"
        "  1. Gallery URL Resolution: `facebook-scraper` is an HTTP parser targeting\n"
        "     m.facebook.com and does NOT support direct navigation of JavaScript\n"
        "     Group Gallery pages (`/groups/<id>/media` or `/photos`). Your supplied\n"
        "     Group Gallery URL will be validated and resolved to its parent Group ID\n"
        "     to extract images from publicly accessible group posts via `get_posts()`.\n"
        "  2. Page Wait Time vs. Download Delay: Because `facebook-scraper` is not a\n"
        "     browser automation tool (like Selenium), the 'Gallery/page loading wait'\n"
        "     does not render a DOM page; instead, it throttles post retrieval requests,\n"
        "     whereas 'Image download delay' pauses between individual CDN file downloads.\n"
        "  Press Enter at any prompt to accept the default value in brackets.\n"
    )

    default_url = (
        getattr(defaults, "url", None)
        or "https://www.facebook.com/groups/foodbloggersbd/media"
    )
    default_max_images = getattr(defaults, "max_images", 100)
    default_post_delay = getattr(defaults, "post_delay", 2.0)
    default_download_delay = getattr(defaults, "download_delay", 1.0)
    default_max_posts = getattr(defaults, "max_posts", 200)
    default_output_dir = getattr(defaults, "output_dir", "facebook_group_dataset")
    default_include_albums = getattr(defaults, "include_albums", True)
    default_timeout = getattr(defaults, "timeout", 30)

    group_url = _prompt_with_default("1. Facebook Group Gallery URL", default_url)
    max_images = _prompt_int(
        "2. Maximum number of images to scrape (e.g. 100, 500, 1000)",
        default=default_max_images,
        min_val=1,
    )
    post_delay = _prompt_float(
        "3. Gallery/page loading wait time (post retrieval delay in seconds)",
        default=default_post_delay,
        min_val=0.0,
    )
    download_delay = _prompt_float(
        "4. Delay between individual image downloads in seconds",
        default=default_download_delay,
        min_val=0.0,
    )
    max_posts = _prompt_int(
        "5. Maximum number of posts to inspect",
        default=default_max_posts,
        min_val=1,
    )
    output_dir_str = _prompt_with_default("6. Output directory", default_output_dir)
    include_albums = _prompt_bool(
        "7. Include gallery albums containing multiple images?",
        default=default_include_albums,
    )
    timeout = _prompt_int(
        "8. HTTP request timeout in seconds",
        default=default_timeout,
        min_val=5,
    )

    print("-" * 72)
    return ScraperConfig(
        group_url=group_url,
        max_images=max_images,
        post_delay=post_delay,
        download_delay=download_delay,
        max_posts=max_posts,
        output_dir=Path(output_dir_str),
        include_multi_image_albums=include_albums,
        request_timeout=timeout,
    )
