"""Facebook Group post and image extraction with strict access-control compliance."""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional

# Suppress RequestsDependencyWarning emitted when facebook-scraper pins urllib3<2
warnings.filterwarnings("ignore", message=".*urllib3.*doesn't match a supported version.*")

import facebook_scraper
from facebook_scraper import exceptions as fb_exceptions
from requests.exceptions import RequestException

from .config import ScraperConfig

logger = logging.getLogger(__name__)


class GroupAccessError(Exception):
    """Raised when Facebook blocks access, requires login, or the group is private/unavailable."""


@dataclass
class ExtractedPostImages:
    """Represents a single inspected Facebook Group post or gallery item and its image URLs."""

    post_id: str
    post_url: str
    caption: str
    image_urls: List[str] = field(default_factory=list)


def upgrade_fbcdn_url_resolution(url: str) -> str:
    """Normalize escaped characters in a CDN URL without stripping access or size constraints."""
    return url.replace("\\/", "/").replace("&amp;", "&").strip()


def extract_images_from_post_dict(
    post: Dict[str, object],
    group_id: str,
    include_multi_image_albums: bool = True,
) -> ExtractedPostImages:
    """Extract normalized metadata and image URLs (`image` and `images`) from a raw post dict.

    Handles malformed or partially populated post dictionaries returned by `facebook-scraper`.
    """
    raw_post_id = post.get("post_id")
    post_id = str(raw_post_id).strip() if raw_post_id is not None else "unknown"

    raw_post_url = post.get("post_url") or post.get("w3_fb_url")
    if raw_post_url and str(raw_post_url).strip():
        post_url = str(raw_post_url).strip()
    elif post_id != "unknown":
        post_url = f"https://www.facebook.com/groups/{group_id}/permalink/{post_id}/"
    else:
        post_url = f"https://www.facebook.com/groups/{group_id}/"

    raw_caption = (
        post.get("post_text")
        or post.get("text")
        or post.get("accessibility_caption")
        or ""
    )
    caption = str(raw_caption).strip()

    discovered: List[str] = []

    def _add_url(candidate: object) -> None:
        if isinstance(candidate, str):
            u = upgrade_fbcdn_url_resolution(candidate)
            if u.startswith(("http://", "https://")) and u not in discovered:
                discovered.append(u)

    # 1. Extract primary `image`
    _add_url(post.get("image"))

    # 2. Extract `images` list (multi-image gallery albums)
    raw_images = post.get("images")
    if isinstance(raw_images, (list, tuple)):
        if include_multi_image_albums:
            for img_url in raw_images:
                _add_url(img_url)
        elif not discovered and len(raw_images) > 0:
            _add_url(raw_images[0])

    # Fallback to low-quality image fields only if HQ fields were completely absent
    if not discovered:
        _add_url(post.get("image_lowquality"))
        raw_lq_images = post.get("images_lowquality")
        if include_multi_image_albums and isinstance(raw_lq_images, (list, tuple)):
            for img_url in raw_lq_images:
                _add_url(img_url)

    return ExtractedPostImages(
        post_id=post_id,
        post_url=post_url,
        caption=caption,
        image_urls=discovered,
    )


class FacebookGroupPostScraper:
    """Extracts group images via `facebook-scraper` without bypassing authentication or anti-bot controls."""

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config

    def iter_group_posts(
        self,
        get_posts_fn: Optional[Callable[..., Iterator[Dict[str, object]]]] = None,
    ) -> Iterator[ExtractedPostImages]:
        """Yield `ExtractedPostImages` from publicly accessible posts in the group.

        Immediately halts and raises `GroupAccessError` if login, rate-limiting, or access
        restrictions are encountered (AGENTS.md §11).
        """
        group_id = self.config.group_id
        posts_inspected = 0

        scraper_fn = get_posts_fn or facebook_scraper.get_posts
        estimated_pages = max(10, (self.config.max_posts // 3) + 5)

        logger.info(
            "Attempting facebook-scraper get_posts(group='%s', page_limit=%d, timeout=%d)",
            group_id,
            estimated_pages,
            self.config.request_timeout,
        )

        try:
            post_iterator = scraper_fn(
                group=group_id,
                page_limit=estimated_pages,
                timeout=self.config.request_timeout,
                options={
                    "allow_extra_requests": False,
                    "HQ_images": True,
                    "reactions": False,
                    "comments": False,
                },
            )

            for raw_post in post_iterator:
                if posts_inspected > 0 and self.config.post_delay > 0:
                    time.sleep(self.config.post_delay)

                if not isinstance(raw_post, dict):
                    continue

                posts_inspected += 1
                try:
                    extracted = extract_images_from_post_dict(
                        raw_post,
                        group_id=group_id,
                        include_multi_image_albums=self.config.include_multi_image_albums,
                    )
                except Exception as exc:
                    logger.warning("Malformed post encountered (skipping): %s", exc)
                    continue

                yield extracted

                if posts_inspected >= self.config.max_posts:
                    logger.info("Reached configured maximum posts to inspect (%d).", self.config.max_posts)
                    return

        except fb_exceptions.LoginRequired as exc:
            raise GroupAccessError(
                f"Facebook requires authentication to access group '{group_id}'. "
                "Stopping in compliance with access-control rules."
            ) from exc
        except (
            fb_exceptions.TemporarilyBanned,
            fb_exceptions.NotFound,
            fb_exceptions.AccountDisabled,
            fb_exceptions.UnexpectedResponse,
        ) as exc:
            raise GroupAccessError(
                f"Facebook restricted access to '{group_id}': {exc}. "
                "Stopping in compliance with access-control rules."
            ) from exc
        except RequestException as exc:
            raise GroupAccessError(f"Network error accessing '{group_id}': {exc}") from exc
