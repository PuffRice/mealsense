"""Image downloader with Requests, exponential backoff, Pillow validation, and SHA-256 deduplication."""

from __future__ import annotations

import hashlib
import io
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, UnidentifiedImageError

from .config import ScraperConfig
from .metadata import ImageMetadata, MetadataManager

logger = logging.getLogger(__name__)

# Map Pillow format names to canonical file extensions (preserving original format)
PILLOW_FORMAT_TO_EXT = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "GIF": "gif",
    "BMP": "bmp",
    "TIFF": "tiff",
    "ICO": "ico",
    "MPO": "jpg",
}

TRANSIENT_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}


@dataclass
class DownloadOutcome:
    """Result of attempting to download and validate a single image URL."""

    status: str  # "downloaded", "duplicate", "failed"
    metadata: Optional[ImageMetadata] = None
    bytes_downloaded: int = 0
    elapsed_seconds: float = 0.0
    error_message: Optional[str] = None


class ImageDownloader:
    """Downloads, validates, deduplicates, and stores images from discovered URLs."""

    def __init__(
        self,
        config: ScraperConfig,
        metadata_manager: MetadataManager,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.config = config
        self.metadata_manager = metadata_manager
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            }
        )
        self._downloads_attempted = 0

    def download_image(
        self,
        image_url: str,
        post_id: str,
        post_url: str,
        post_caption: str,
    ) -> DownloadOutcome:
        """Download a single image, validate via Pillow, deduplicate by SHA-256, and save."""
        # Fast-path URL deduplication
        if self.metadata_manager.is_url_seen(image_url):
            logger.debug("Skipping duplicate image URL: %s", image_url)
            return DownloadOutcome(status="duplicate")

        # Respect configured delay between individual image downloads
        if self._downloads_attempted > 0 and self.config.download_delay > 0:
            time.sleep(self.config.download_delay)
        self._downloads_attempted += 1

        start_time = time.perf_counter()
        raw_bytes, error_msg = self._fetch_bytes_with_backoff(image_url)
        elapsed = max(time.perf_counter() - start_time, 1e-6)

        if raw_bytes is None:
            logger.warning("Failed to download image %s: %s", image_url, error_msg)
            return DownloadOutcome(
                status="failed",
                elapsed_seconds=elapsed,
                error_message=error_msg,
            )

        # Compute SHA-256 hash before writing to disk
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        if self.metadata_manager.is_hash_seen(sha256_hash):
            logger.info("Duplicate image detected via SHA-256 (%s) for URL %s", sha256_hash[:12], image_url)
            return DownloadOutcome(
                status="duplicate",
                bytes_downloaded=len(raw_bytes),
                elapsed_seconds=elapsed,
            )

        # Validate image integrity and extract dimensions & format with Pillow
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.verify()
            # Re-open after verify() to read width, height, and format reliably
            with Image.open(io.BytesIO(raw_bytes)) as img:
                width, height = img.size
                img_format = (img.format or "").upper()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            msg = f"Corrupted or non-image content rejected by Pillow: {exc}"
            logger.warning("%s (URL: %s)", msg, image_url)
            return DownloadOutcome(
                status="failed",
                bytes_downloaded=len(raw_bytes),
                elapsed_seconds=elapsed,
                error_message=msg,
            )

        if width <= 0 or height <= 0:
            msg = f"Invalid image dimensions ({width}x{height})"
            logger.warning("%s (URL: %s)", msg, image_url)
            return DownloadOutcome(
                status="failed",
                bytes_downloaded=len(raw_bytes),
                elapsed_seconds=elapsed,
                error_message=msg,
            )

        ext = PILLOW_FORMAT_TO_EXT.get(img_format, img_format.lower() if img_format else "jpg")
        filename = self.metadata_manager.allocate_filename(ext)
        file_path: Path = self.config.images_dir / filename

        # Write atomically via temporary file so interrupted writes never leave corrupted files
        temp_path = file_path.with_suffix(file_path.suffix + ".part")
        try:
            temp_path.write_bytes(raw_bytes)
            temp_path.replace(file_path)
        except OSError as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            msg = f"Filesystem error saving {file_path}: {exc}"
            logger.error(msg)
            return DownloadOutcome(
                status="failed",
                bytes_downloaded=len(raw_bytes),
                elapsed_seconds=elapsed,
                error_message=msg,
            )

        timestamp = datetime.now(timezone.utc).isoformat()
        record = ImageMetadata(
            filename=filename,
            original_image_url=image_url,
            post_id=post_id,
            post_url=post_url,
            post_caption=post_caption,
            group_id=self.config.group_id,
            download_timestamp=timestamp,
            width=width,
            height=height,
            file_size_bytes=len(raw_bytes),
            sha256_hash=sha256_hash,
            download_status="success",
        )
        self.metadata_manager.add_record(record)
        logger.info(
            "Saved %s (%dx%d, %d bytes, sha256=%s...)",
            filename,
            width,
            height,
            len(raw_bytes),
            sha256_hash[:12],
        )

        return DownloadOutcome(
            status="downloaded",
            metadata=record,
            bytes_downloaded=len(raw_bytes),
            elapsed_seconds=elapsed,
        )

    def _fetch_bytes_with_backoff(self, url: str) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch raw image bytes using conservative retries and exponential backoff."""
        max_attempts = self.config.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.config.request_timeout,
                    stream=True,
                )
                status = response.status_code

                # Expired Facebook CDN URLs often return 403 Forbidden or 404/410
                if status in (403, 404, 410):
                    return None, f"Expired or inaccessible image URL (HTTP {status})"

                if status in TRANSIENT_HTTP_STATUSES and attempt < max_attempts:
                    wait_s = self.config.backoff_factor ** attempt
                    logger.warning(
                        "Transient HTTP %d for %s (attempt %d/%d). Backing off %.1fs...",
                        status,
                        url,
                        attempt,
                        max_attempts,
                        wait_s,
                    )
                    time.sleep(wait_s)
                    continue

                response.raise_for_status()

                content_type = (response.headers.get("Content-Type") or "").lower()
                if content_type and not (
                    content_type.startswith("image/")
                    or "octet-stream" in content_type
                ):
                    return None, f"Non-image Content-Type response: '{content_type}'"

                # Read streamed chunks to handle interrupted downloads cleanly
                chunks = []
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        chunks.append(chunk)
                data = b"".join(chunks)
                if not data:
                    return None, "Empty response body"
                return data, None

            except requests.RequestException as exc:
                if attempt < max_attempts:
                    wait_s = self.config.backoff_factor ** attempt
                    logger.warning(
                        "Network error downloading %s (attempt %d/%d): %s. Retrying in %.1fs...",
                        url,
                        attempt,
                        max_attempts,
                        exc,
                        wait_s,
                    )
                    time.sleep(wait_s)
                else:
                    return None, f"Request failed after {max_attempts} attempts: {exc}"

        return None, "Maximum retry attempts exceeded"
