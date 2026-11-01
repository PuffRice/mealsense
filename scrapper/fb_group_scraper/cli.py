"""Orchestration and CLI entrypoint for the Facebook Group Gallery Image Scraper."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Dict, Iterator, Optional

import requests

from .config import ScraperConfig, build_arg_parser, prompt_interactive_config
from .downloader import ImageDownloader
from .food_filter import filter_and_move_food_images
from .logger import setup_logging
from .metadata import MetadataManager
from .reporter import (
    ProgressDashboard,
    ScrapingStats,
    format_report_summary,
    generate_final_report,
)
from .scraper import FacebookGroupPostScraper, GroupAccessError
from .validator import ValidationError, validate_all

logger = logging.getLogger(__name__)


def _run_food_filter_and_print_summary(config: ScraperConfig) -> Dict[str, object]:
    """Run the vision food classifier to move food images into `food_images/` and print summary."""
    print(
        f"\n[Vision Food Filter] Classifying images in '{config.output_dir}' using "
        f"Hugging Face TinyCLIP (threshold={config.food_confidence_threshold:.2f})..."
    )
    food_report = filter_and_move_food_images(
        dataset_dir=config.output_dir,
        food_dir_name="food_images",
        non_food_dir_name="non_food_images",
        confidence_threshold=config.food_confidence_threshold,
        show_progress=True,
    )
    print(
        f"  -> Evaluated this run : {food_report['total_images_evaluated_this_run']}\n"
        f"  -> Food images kept   : {food_report['food_images_moved_this_run']} "
        f"(Saved in '{config.food_images_dir.resolve()}')\n"
        f"  -> Non-food filtered  : {food_report['non_food_images_filtered_out_this_run']} "
        f"(Moved to '{config.non_food_images_dir.resolve()}')\n"
        f"  -> Food metadata saved: {(config.metadata_dir / 'food_images_metadata.csv').resolve()}"
    )
    return food_report


def run_scraping_pipeline(
    config: ScraperConfig,
    check_network: bool = True,
    enable_live_dashboard: bool = True,
    get_posts_fn: Optional[Callable[..., Iterator[Dict[str, object]]]] = None,
    http_session: Optional[requests.Session] = None,
) -> Dict[str, object]:
    """Execute the complete 4-step Facebook Group image scraping workflow.

    Steps:
    1. Validate configuration, Group Gallery URL, output directories, and network connectivity.
    2. Extract group posts using `facebook-scraper`'s `get_posts(group=...)`.
    3. Download, validate (Pillow), and deduplicate (SHA-256) images via Requests.
    4. Save incremental metadata (CSV + JSON) and generate the final scraping report.
    """
    # Step 1: Input validation & directory setup
    parsed_url = validate_all(config, check_network=check_network)
    setup_logging(config.log_file_path)

    logger.info("Initialized scraping session for URL: %s", config.group_url)
    if parsed_url.is_gallery_subpage:
        msg = (
            f"[Info] Resolved Group Gallery URL ('/{parsed_url.detected_subpath}') "
            f"to group identifier '{parsed_url.group_id}'. Will attempt `facebook-scraper` "
            f"get_posts(group='{parsed_url.group_id}') and automatically activate high-resolution "
            f"Comet Group Gallery pagination (scale=16) if legacy m.facebook.com returns 0 posts."
        )
        print(msg)
        logger.info(msg)

    metadata_manager = MetadataManager(
        csv_path=config.metadata_csv_path,
        json_path=config.metadata_json_path,
        images_dir=config.images_dir,
        resume=config.resume,
    )
    # Ensure metadata files exist right away
    metadata_manager.save()

    resumed_count = len(metadata_manager.records)
    if resumed_count > 0:
        print(
            f"[Resume] Found {resumed_count} previously downloaded image(s) in "
            f"'{config.output_dir}'. Resuming session without discarding existing files."
        )

    stats = ScrapingStats(
        group_url=config.group_url,
        group_id=config.group_id,
        target_images=config.max_images,
        images_downloaded=resumed_count,
        resumed_images_count=resumed_count,
    )

    if stats.images_downloaded >= config.max_images:
        stats.termination_reason = (
            f"Target image count ({config.max_images}) already satisfied by resumed dataset"
        )
        if config.filter_food_only and get_posts_fn is None:
            _run_food_filter_and_print_summary(config)
        report = generate_final_report(stats, metadata_manager.records, config.report_json_path)
        print(format_report_summary(report))
        return report

    post_scraper = FacebookGroupPostScraper(config)
    downloader = ImageDownloader(config, metadata_manager, session=http_session)

    try:
        with ProgressDashboard(stats, enabled=enable_live_dashboard) as dashboard:
            for post_data in post_scraper.iter_group_posts(get_posts_fn=get_posts_fn):
                stats.posts_inspected += 1
                stats.current_post_id = post_data.post_id
                stats.images_discovered += len(post_data.image_urls)
                dashboard.update()

                for img_url in post_data.image_urls:
                    if stats.images_downloaded >= config.max_images:
                        break

                    outcome = downloader.download_image(
                        image_url=img_url,
                        post_id=post_data.post_id,
                        post_url=post_data.post_url,
                        post_caption=post_data.caption,
                    )

                    if outcome.status == "downloaded":
                        stats.images_downloaded += 1
                        stats.total_bytes_downloaded += outcome.bytes_downloaded
                        stats.active_download_seconds += outcome.elapsed_seconds
                        if outcome.elapsed_seconds > 0:
                            stats.last_speed_kbps = (
                                outcome.bytes_downloaded / 1024.0
                            ) / outcome.elapsed_seconds
                    elif outcome.status == "duplicate":
                        stats.duplicate_images += 1
                    else:
                        stats.failed_downloads += 1

                    dashboard.update()

                if stats.images_downloaded >= config.max_images:
                    stats.termination_reason = (
                        f"Reached target image limit ({config.max_images})"
                    )
                    logger.info(stats.termination_reason)
                    dashboard.update()
                    break
            else:
                if stats.posts_inspected == 0:
                    stats.termination_reason = (
                        "No publicly accessible posts were returned by facebook-scraper. "
                        "Facebook typically restricts unauthenticated access to group feeds "
                        "or requires login cookies."
                    )
                elif stats.posts_inspected >= config.max_posts:
                    stats.termination_reason = (
                        f"Reached maximum inspected posts limit ({config.max_posts})"
                    )
                else:
                    stats.termination_reason = "Exhausted all available group posts"

    except GroupAccessError as exc:
        stats.termination_reason = f"Stopped due to Facebook access restriction: {exc}"
        print(f"\n[Access Restricted] {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        stats.termination_reason = "Interrupted by user (Ctrl+C); progress saved"
        print("\n[Interrupted] Session stopped by user. Saving collected metadata...", file=sys.stderr)
    except Exception as exc:
        stats.termination_reason = f"Unexpected error: {exc}"
        logger.exception("Unexpected error during scraping session")
        print(f"\n[Error] Unexpected error occurred: {exc}", file=sys.stderr)

    # Always save metadata and final report without discarding already downloaded images
    metadata_manager.save()
    if config.filter_food_only and get_posts_fn is None:
        _run_food_filter_and_print_summary(config)
    report = generate_final_report(stats, metadata_manager.records, config.report_json_path)
    print(format_report_summary(report))
    return report


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.filter_only:
        config = ScraperConfig(
            group_url=args.url or "https://www.facebook.com/groups/foodbloggersbd/media",
            output_dir=Path(args.output_dir),
            filter_food_only=True,
            food_confidence_threshold=args.food_threshold,
        )
        _run_food_filter_and_print_summary(config)
        return 0

    if args.non_interactive:
        if not args.url:
            parser.error("--url is required when running with --non-interactive")
        config = ScraperConfig(
            group_url=args.url,
            max_images=args.max_images,
            post_delay=args.post_delay,
            download_delay=args.download_delay,
            max_posts=args.max_posts,
            output_dir=Path(args.output_dir),
            include_multi_image_albums=args.include_albums,
            request_timeout=args.timeout,
            max_retries=args.max_retries,
            resume=args.resume,
            filter_food_only=args.filter_food,
            food_confidence_threshold=args.food_threshold,
        )
    elif args.url is not None:
        config = ScraperConfig(
            group_url=args.url,
            max_images=args.max_images,
            post_delay=args.post_delay,
            download_delay=args.download_delay,
            max_posts=args.max_posts,
            output_dir=Path(args.output_dir),
            include_multi_image_albums=args.include_albums,
            request_timeout=args.timeout,
            max_retries=args.max_retries,
            resume=args.resume,
            filter_food_only=args.filter_food,
            food_confidence_threshold=args.food_threshold,
        )
    else:
        config = prompt_interactive_config(defaults=args)

    try:
        run_scraping_pipeline(config)
        return 0
    except ValidationError as exc:
        print(f"\n[Configuration / Validation Error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
