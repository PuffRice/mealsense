"""Input, filesystem, and network validation for the Facebook Group Image Scraper."""

from __future__ import annotations

import logging
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from .config import ScraperConfig

logger = logging.getLogger(__name__)

# Valid Facebook domains
VALID_FB_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "mbasic.facebook.com",
    "web.facebook.com",
}

# Known gallery/subpage path segments under /groups/<group_id>/...
GALLERY_SUBPATHS = {
    "media",
    "photos",
    "albums",
    "files",
    "videos",
    "about",
    "discussion",
    "members",
    "events",
    "announcements",
    "featured",
    "buy_sell_discussion",
}


class ValidationError(Exception):
    """Raised when configuration, URL, filesystem, or network validation fails."""


@dataclass(frozen=True)
class ParsedGroupURL:
    """Result of validating and parsing a Facebook Group / Group Gallery URL."""

    original_url: str
    normalized_group_url: str
    group_id: str
    is_gallery_subpage: bool
    detected_subpath: Optional[str]


def parse_and_validate_group_url(url: str) -> ParsedGroupURL:
    """Validate a Facebook Group or Group Gallery URL and extract the group identifier.

    Supports URLs such as:
    - https://www.facebook.com/groups/1234567890/media
    - https://www.facebook.com/groups/my_group_slug/photos
    - https://m.facebook.com/groups/my_group_slug/media/albums
    - https://www.facebook.com/groups/my_group_slug/

    Raises:
        ValidationError: If the URL is malformed, not a Facebook URL, or lacks a group ID.
    """
    if not url or not url.strip():
        raise ValidationError("Facebook Group URL cannot be empty.")

    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned

    parsed = urlparse(cleaned)
    hostname = (parsed.hostname or "").lower()

    if hostname not in VALID_FB_DOMAINS:
        raise ValidationError(
            f"Invalid domain '{hostname}'. Expected a Facebook domain "
            f"({', '.join(sorted(VALID_FB_DOMAINS))})."
        )

    # Split path segments: e.g., /groups/<group_id>/media/photos
    segments = [seg for seg in parsed.path.split("/") if seg]
    if len(segments) < 2 or segments[0].lower() != "groups":
        raise ValidationError(
            f"URL path '{parsed.path}' is not a valid Facebook Group path. "
            "Expected format: https://www.facebook.com/groups/<group_id_or_slug>[/media|/photos]"
        )

    group_id = segments[1].strip()
    if not group_id or group_id.lower() in GALLERY_SUBPATHS:
        raise ValidationError(
            f"Could not extract a valid group identifier from URL: '{url}'."
        )

    # Validate characters in group_id (alphanumeric, dots, hyphens, underscores)
    if not re.match(r"^[A-Za-z0-9._-]+$", group_id):
        raise ValidationError(
            f"Extracted group identifier '{group_id}' contains invalid characters."
        )

    subpath: Optional[str] = None
    is_gallery = False
    if len(segments) > 2:
        subpath = "/".join(segments[2:])
        if any(seg.lower() in {"media", "photos", "albums"} for seg in segments[2:]):
            is_gallery = True

    normalized_group_url = f"https://www.facebook.com/groups/{group_id}/"
    return ParsedGroupURL(
        original_url=url.strip(),
        normalized_group_url=normalized_group_url,
        group_id=group_id,
        is_gallery_subpage=is_gallery,
        detected_subpath=subpath,
    )


def validate_numeric_config(config: ScraperConfig) -> None:
    """Validate all numeric limits, delays, and timeout settings in `ScraperConfig`."""
    if config.max_images < 1:
        raise ValidationError(f"max_images must be >= 1 (got {config.max_images}).")
    if config.max_posts < 1:
        raise ValidationError(f"max_posts must be >= 1 (got {config.max_posts}).")
    if config.post_delay < 0:
        raise ValidationError(f"post_delay must be >= 0.0 seconds (got {config.post_delay}).")
    if config.download_delay < 0:
        raise ValidationError(
            f"download_delay must be >= 0.0 seconds (got {config.download_delay})."
        )
    if config.request_timeout < 1:
        raise ValidationError(
            f"request_timeout must be >= 1 second (got {config.request_timeout})."
        )
    if config.max_retries < 0:
        raise ValidationError(f"max_retries must be >= 0 (got {config.max_retries}).")


def validate_and_prepare_directories(config: ScraperConfig) -> None:
    """Create the output directory structure and verify write permissions.

    Structure created:
    - `<output_dir>/images/`
    - `<output_dir>/metadata/`
    - `<output_dir>/logs/`
    """
    target_dirs = [
        config.output_dir,
        config.images_dir,
        config.metadata_dir,
        config.logs_dir,
    ]
    for directory in target_dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValidationError(
                f"Failed to create directory '{directory}': {exc}"
            ) from exc

    # Verify write permission by creating and removing a temporary probe file
    probe_file = config.output_dir / ".write_permission_probe"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
    except OSError as exc:
        raise ValidationError(
            f"Output directory '{config.output_dir}' is not writable: {exc}"
        ) from exc


def check_network_connectivity(timeout: int = 10) -> bool:
    """Check network connectivity and DNS resolution to Facebook before scraping.

    Raises:
        ValidationError: If DNS resolution or basic HTTPS connection fails.
    """
    host = "m.facebook.com"
    try:
        socket.getaddrinfo(host, 443)
    except socket.gaierror as exc:
        raise ValidationError(
            f"Network connectivity check failed: Unable to resolve '{host}' ({exc}). "
            "Please check your internet connection and DNS settings."
        ) from exc

    try:
        resp = requests.head(
            f"https://{host}/",
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
            allow_redirects=True,
        )
        logger.debug("Network check to %s returned HTTP %s", host, resp.status_code)
        return True
    except requests.RequestException as exc:
        raise ValidationError(
            f"Network connectivity check failed when connecting to https://{host}/: {exc}"
        ) from exc


def validate_all(config: ScraperConfig, check_network: bool = True) -> ParsedGroupURL:
    """Run all Step 1 input validations and populate `config.group_id`."""
    validate_numeric_config(config)
    parsed_url = parse_and_validate_group_url(config.group_url)
    config.group_id = parsed_url.group_id
    validate_and_prepare_directories(config)
    if check_network:
        check_network_connectivity(timeout=min(config.request_timeout, 15))
    return parsed_url
