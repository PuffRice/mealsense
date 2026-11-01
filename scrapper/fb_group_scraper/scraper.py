"""Facebook Group post and high-resolution Group Gallery image extraction."""

from __future__ import annotations

import json
import logging
import re
import time
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional

# Suppress RequestsDependencyWarning emitted when facebook-scraper pins urllib3<2
warnings.filterwarnings("ignore", message=".*urllib3.*doesn't match a supported version.*")

import facebook_scraper
from facebook_scraper import exceptions as fb_exceptions
import requests
from requests.exceptions import RequestException

from .config import ScraperConfig

logger = logging.getLogger(__name__)

# Default Relay operation ID for Facebook Group Media/Photos Tab Grid pagination
DEFAULT_GALLERY_PAGINATION_DOC_ID = "26680580074858996"
DEFAULT_GALLERY_ROOT_DOC_ID = "34206624742316139"

BROWSER_NAVIGATION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


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
    """Upgrade a Facebook CDN (`scontent`) URL to maximum available resolution when safe.

    When Facebook embeds a `cstp=mx<W>x<H>&ctp=p<w>x<h>` pair in the query string,
    removing the `ctp=...` thumbnail constraint while preserving `stp` and `cstp`
    causes the CDN to serve the full `mx<W>x<H>` resolution with the same `oh`/`oe`
    signature.
    """
    cleaned = url.replace("\\/", "/").replace("&amp;", "&").strip()
    if "cstp=" in cleaned and "&ctp=" in cleaned:
        cleaned = re.sub(r"&ctp=[^&]+", "", cleaned)
    return cleaned


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
    """Extracts group images via `facebook-scraper` and Facebook Comet Group Gallery Relay API.

    Workflow:
    1. If a custom `get_posts_fn` is injected (e.g., in unit tests) or `facebook-scraper`'s
       `get_posts(group=...)` returns legacy mobile posts, it extracts `image` and `images`.
    2. Because Facebook has retired `m.facebook.com` HTML `<article>` feeds and redirects
       public groups to Comet SSR (`www.facebook.com/groups/<group>/media`), when
       `facebook-scraper` returns 0 posts on a live group, this scraper automatically
       queries the public Group Gallery & Feed Comet Relay endpoints with `scale=16` to
       retrieve uncropped, full-resolution original images (up to 2048px) directly from
       the Group Gallery (`group_mediaset`).
    """

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config

    def iter_group_posts(
        self,
        get_posts_fn: Optional[Callable[..., Iterator[Dict[str, object]]]] = None,
    ) -> Iterator[ExtractedPostImages]:
        """Yield `ExtractedPostImages` from publicly accessible posts/media in the group."""
        group_id = self.config.group_id
        posts_inspected = 0

        # If a custom get_posts_fn was provided (or we attempt facebook_scraper.get_posts first)
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
                    "allow_extra_requests": True,
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
            if get_posts_fn is not None:
                raise GroupAccessError(
                    f"Facebook requires authentication (login/cookies) to access group '{group_id}'."
                ) from exc
            logger.info("facebook-scraper hit LoginRequired on m.facebook.com; trying public Comet Gallery...")
        except (
            fb_exceptions.TemporarilyBanned,
            fb_exceptions.NotFound,
            fb_exceptions.AccountDisabled,
            fb_exceptions.UnexpectedResponse,
        ) as exc:
            if get_posts_fn is not None:
                raise GroupAccessError(f"Facebook restricted access to '{group_id}': {exc}") from exc
            logger.info("facebook-scraper encountered %s on m.facebook.com; trying public Comet Gallery...", type(exc).__name__)
        except RequestException as exc:
            if get_posts_fn is not None:
                raise GroupAccessError(f"Network error accessing '{group_id}': {exc}") from exc
            logger.info("facebook-scraper RequestException (%s); trying public Comet Gallery...", exc)

        # If a custom mock function was injected for testing, do not make live network fallback calls
        if get_posts_fn is not None or posts_inspected > 0:
            return

        logger.info(
            "facebook-scraper returned 0 posts (m.facebook.com legacy HTML deprecated). "
            "Activating high-resolution Comet Group Gallery & Feed extractor for '%s'...",
            group_id,
        )
        yield from self._iter_comet_group_gallery_and_feed()

    def _iter_comet_group_gallery_and_feed(self) -> Iterator[ExtractedPostImages]:
        """Extract high-resolution images from the public Group Gallery (`/media`) and Group Feed."""
        session = requests.Session()
        session.headers.update(BROWSER_NAVIGATION_HEADERS)

        gallery_url = f"https://www.facebook.com/groups/{self.config.group_id}/media"
        logger.info("Fetching Group Gallery page: %s", gallery_url)

        try:
            resp = session.get(gallery_url, timeout=self.config.request_timeout)
            resp.raise_for_status()
        except RequestException as exc:
            raise GroupAccessError(
                f"Failed to load Facebook Group Gallery URL '{gallery_url}': {exc}"
            ) from exc

        html = resp.text

        # Extract LSD token and numeric groupID required for Comet GraphQL pagination
        lsd_match = re.search(r'"LSD",\[\],\{"token":"([^"]+)"\}', html)
        numeric_group_match = (
            re.search(r'"groupID":"(\d+)"', html)
            or re.search(r'"target_group":\{"id":"(\d+)"', html)
            or re.search(r'"entity_id":"(\d+)"', html)
        )

        if not numeric_group_match:
            if "login" in resp.url.lower() or "log in to facebook" in html.lower():
                raise GroupAccessError(
                    f"Facebook requires login to view group '{self.config.group_id}'. "
                    "The group may be private or restricted."
                )
            raise GroupAccessError(
                f"Could not resolve numeric Facebook Group ID from '{gallery_url}'. "
                "The group may be private, deleted, or unavailable."
            )

        numeric_group_id = numeric_group_match.group(1)
        lsd_token = lsd_match.group(1) if lsd_match else ""
        pagination_doc_id = self._discover_gallery_doc_id(html, session)

        logger.info(
            "Resolved Group '%s' -> numeric ID %s (LSD=%s, gallery_doc_id=%s)",
            self.config.group_id,
            numeric_group_id,
            bool(lsd_token),
            pagination_doc_id,
        )

        posts_inspected = 0
        seen_photo_ids: set[str] = set()

        # 1. Paginate through Group Gallery (`GroupsCometMediaPhotosTabGridQuery`) with scale=16
        # Using scale=16 instructs Facebook's CDN URL generator to emit uncropped, full-resolution
        # image URLs (matching `viewer_image` dimensions up to 2048x2048) instead of 110x80 thumbnails!
        if lsd_token:
            cursor: Optional[str] = None
            has_next_page = True
            page_index = 0

            while has_next_page and posts_inspected < self.config.max_posts:
                if page_index > 0 and self.config.post_delay > 0:
                    logger.debug(
                        "Sleeping %.2fs (gallery page loading wait time)...",
                        self.config.post_delay,
                    )
                    time.sleep(self.config.post_delay)

                page_index += 1
                edges, next_cursor, has_next = self._fetch_gallery_graphql_page(
                    session=session,
                    lsd_token=lsd_token,
                    numeric_group_id=numeric_group_id,
                    cursor=cursor,
                    doc_id=pagination_doc_id,
                    referer=gallery_url,
                )

                if not edges:
                    logger.info("Gallery GraphQL page %d returned 0 edges; stopping pagination.", page_index)
                    break

                for edge in edges:
                    node = edge.get("node") if isinstance(edge, dict) else None
                    if not isinstance(node, dict):
                        continue

                    photo_id = str(node.get("id") or "").strip()
                    if not photo_id or photo_id in seen_photo_ids:
                        continue

                    img_obj = node.get("image")
                    raw_uri = img_obj.get("uri") if isinstance(img_obj, dict) else None
                    if not raw_uri or not isinstance(raw_uri, str):
                        continue

                    hq_uri = upgrade_fbcdn_url_resolution(raw_uri)
                    seen_photo_ids.add(photo_id)
                    posts_inspected += 1

                    caption = str(node.get("accessibility_caption") or "").strip()
                    photo_url = (
                        f"https://www.facebook.com/photo/?fbid={photo_id}&set=g.{numeric_group_id}"
                    )

                    yield ExtractedPostImages(
                        post_id=photo_id,
                        post_url=photo_url,
                        caption=caption,
                        image_urls=[hq_uri],
                    )

                    if posts_inspected >= self.config.max_posts:
                        logger.info("Reached maximum posts/media items to inspect (%d).", self.config.max_posts)
                        return

                cursor = next_cursor
                has_next_page = bool(has_next and cursor)

        # 2. Fallback: if GraphQL pagination yielded nothing, parse embedded SSR JSON from HTML
        if posts_inspected == 0:
            logger.info("Parsing embedded SSR JSON blocks from Group Gallery HTML...")
            for item in self._extract_ssr_gallery_and_feed_items(html, numeric_group_id):
                if item.post_id in seen_photo_ids:
                    continue
                seen_photo_ids.add(item.post_id)
                posts_inspected += 1
                yield item
                if posts_inspected >= self.config.max_posts:
                    return

    def _discover_gallery_doc_id(self, html: str, session: requests.Session) -> str:
        """Attempt to dynamically discover `GroupsCometMediaPhotosTabGridQuery` doc_id if needed."""
        # Check if HTML or its primary bundle specifies a newer doc_id; otherwise use verified default
        match = re.search(
            r'GroupsCometMediaPhotosTabGridQuery_facebookRelayOperation"[^"]*"(\d+)"',
            html,
        )
        if match:
            return match.group(1)
        return DEFAULT_GALLERY_PAGINATION_DOC_ID

    def _fetch_gallery_graphql_page(
        self,
        session: requests.Session,
        lsd_token: str,
        numeric_group_id: str,
        cursor: Optional[str],
        doc_id: str,
        referer: str,
    ) -> tuple[List[Dict[str, object]], Optional[str], bool]:
        """Request a page of high-resolution photos from `GroupsCometMediaPhotosTabGridQuery`."""
        graphql_headers = {
            "User-Agent": BROWSER_NAVIGATION_HEADERS["User-Agent"],
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-FB-LSD": lsd_token,
            "X-FB-Friendly-Name": "GroupsCometMediaPhotosTabGridQuery",
            "Origin": "https://www.facebook.com",
            "Referer": referer,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        variables = {
            "count": 8,
            "cursor": cursor,
            "id": numeric_group_id,
            "scale": 16,  # Critical: scale=16 returns full-resolution uncropped image URLs
        }

        payload = {
            "av": "0",
            "__user": "0",
            "__a": "1",
            "lsd": lsd_token,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "GroupsCometMediaPhotosTabGridQuery",
            "variables": json.dumps(variables),
            "server_timestamps": "true",
            "doc_id": doc_id,
        }

        max_attempts = self.config.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                resp = session.post(
                    "https://www.facebook.com/api/graphql/",
                    headers=graphql_headers,
                    data=payload,
                    timeout=self.config.request_timeout,
                )
                resp.raise_for_status()

                text = resp.text.strip()
                if text.startswith("for (;;);"):
                    text = text[len("for (;;);") :].strip()
                # Handle multi-line JSON objects if Facebook streams chunks
                first_line = text.splitlines()[0] if text else "{}"
                data = json.loads(first_line)

                node = data.get("data", {}).get("node") or data.get("data", {}).get("group") or {}
                mediaset = node.get("group_mediaset") or {}
                media = mediaset.get("media") or {}
                edges = media.get("edges") or []
                page_info = media.get("page_info") or {}
                end_cursor = page_info.get("end_cursor")
                has_next_page = bool(page_info.get("has_next_page"))
                return edges, end_cursor, has_next_page

            except (RequestException, ValueError, KeyError) as exc:
                if attempt < max_attempts:
                    wait_s = self.config.backoff_factor ** attempt
                    logger.warning(
                        "Gallery GraphQL request error (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt,
                        max_attempts,
                        exc,
                        wait_s,
                    )
                    time.sleep(wait_s)
                else:
                    logger.error("Gallery GraphQL request failed after %d attempts: %s", max_attempts, exc)
                    return [], None, False

        return [], None, False

    def _extract_ssr_gallery_and_feed_items(
        self,
        html: str,
        numeric_group_id: str,
    ) -> List[ExtractedPostImages]:
        """Parse embedded `<script type="application/json">` SSR blocks for high-res photo nodes."""
        items: List[ExtractedPostImages] = []
        seen_urls: set[str] = set()

        # Match Photo nodes inside group_mediaset or story attachments
        photo_pattern = re.compile(
            r'\{"__typename":"Photo","id":"(\d+)"(?:,"accessibility_caption":(null|"[^"]*"))?'
            r'(?:,[^{}]*)?,"image":\{"uri":"(https:[^"]+)"\}',
        )
        for match in photo_pattern.finditer(html):
            photo_id = match.group(1)
            raw_caption = match.group(2)
            raw_uri = match.group(3).encode("utf-8").decode("unicode_escape")
            hq_uri = upgrade_fbcdn_url_resolution(raw_uri)

            if hq_uri in seen_urls:
                continue
            seen_urls.add(hq_uri)

            caption = ""
            if raw_caption and raw_caption != "null":
                try:
                    caption = json.loads(raw_caption)
                except Exception:
                    caption = raw_caption.strip('"')

            items.append(
                ExtractedPostImages(
                    post_id=photo_id,
                    post_url=f"https://www.facebook.com/photo/?fbid={photo_id}&set=g.{numeric_group_id}",
                    caption=caption,
                    image_urls=[hq_uri],
                )
            )

        return items
