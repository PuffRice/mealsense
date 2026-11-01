"""Incremental metadata management and resumability for downloaded images."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

logger = logging.getLogger(__name__)

METADATA_COLUMNS = [
    "filename",
    "original_image_url",
    "post_id",
    "post_url",
    "post_caption",
    "group_id",
    "download_timestamp",
    "width",
    "height",
    "file_size_bytes",
    "sha256_hash",
    "download_status",
]


@dataclass
class ImageMetadata:
    """Metadata record for a single downloaded image."""

    filename: str
    original_image_url: str
    post_id: str
    post_url: str
    post_caption: str
    group_id: str
    download_timestamp: str
    width: int
    height: int
    file_size_bytes: int
    sha256_hash: str
    download_status: str = "success"

    def to_dict(self) -> Dict[str, object]:
        """Convert metadata record to a serializable dictionary."""
        return asdict(self)


class MetadataManager:
    """Manages incremental persistence of image metadata to CSV and JSON using Pandas.

    Also supports resuming an interrupted scraping session by loading previously
    recorded SHA-256 hashes, image URLs, and file sequence numbers so already
    downloaded images are never discarded or re-downloaded.
    """

    def __init__(
        self,
        csv_path: Path,
        json_path: Path,
        images_dir: Path,
        resume: bool = True,
    ) -> None:
        self.csv_path = csv_path
        self.json_path = json_path
        self.images_dir = images_dir
        self.records: List[ImageMetadata] = []
        self.seen_hashes: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self._next_index: int = 1

        if resume:
            self._load_existing()

    def _load_existing(self) -> None:
        """Load existing metadata from JSON or CSV and scan the images directory."""
        loaded_dicts: List[Dict[str, object]] = []

        if self.json_path.exists():
            try:
                raw = json.loads(self.json_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    loaded_dicts = raw
                    logger.info(
                        "Resumed %d existing metadata records from %s",
                        len(loaded_dicts),
                        self.json_path,
                    )
            except Exception as exc:
                logger.warning("Could not read existing JSON metadata (%s): %s", self.json_path, exc)

        if not loaded_dicts and self.csv_path.exists():
            try:
                df = pd.read_csv(self.csv_path, dtype=str).fillna("")
                loaded_dicts = df.to_dict(orient="records")
                logger.info(
                    "Resumed %d existing metadata records from %s",
                    len(loaded_dicts),
                    self.csv_path,
                )
            except Exception as exc:
                logger.warning("Could not read existing CSV metadata (%s): %s", self.csv_path, exc)

        for item in loaded_dicts:
            try:
                record = ImageMetadata(
                    filename=str(item.get("filename", "")),
                    original_image_url=str(item.get("original_image_url", "")),
                    post_id=str(item.get("post_id", "")),
                    post_url=str(item.get("post_url", "")),
                    post_caption=str(item.get("post_caption", "")),
                    group_id=str(item.get("group_id", "")),
                    download_timestamp=str(item.get("download_timestamp", "")),
                    width=int(float(item.get("width", 0) or 0)),
                    height=int(float(item.get("height", 0) or 0)),
                    file_size_bytes=int(float(item.get("file_size_bytes", 0) or 0)),
                    sha256_hash=str(item.get("sha256_hash", "")),
                    download_status=str(item.get("download_status", "success")),
                )
                self.records.append(record)
                if record.sha256_hash:
                    self.seen_hashes.add(record.sha256_hash)
                if record.original_image_url:
                    self.seen_urls.add(record.original_image_url)
                self._update_index_from_filename(record.filename)
            except Exception as exc:
                logger.warning("Skipping malformed metadata record during resume: %s", exc)

        # Also inspect existing files in images_dir and food_images / non_food_images so we never overwrite an existing image
        for candidate_dir in (
            self.images_dir,
            self.images_dir.parent / "food_images",
            self.images_dir.parent / "non_food_images",
        ):
            if candidate_dir.exists():
                for existing_file in candidate_dir.iterdir():
                    if existing_file.is_file():
                        self._update_index_from_filename(existing_file.name)

    def _update_index_from_filename(self, filename: str) -> None:
        """Advance `_next_index` past any existing `image_XXXXXX.<ext>` filename."""
        match = re.match(r"^image_(\d+)\.[A-Za-z0-9]+$", filename)
        if match:
            idx = int(match.group(1))
            if idx >= self._next_index:
                self._next_index = idx + 1

    def allocate_filename(self, extension: str) -> str:
        """Return the next sequential filename `image_000001.<ext>` and increment counter."""
        ext = extension.lstrip(".").lower() or "jpg"
        filename = f"image_{self._next_index:06d}.{ext}"
        self._next_index += 1
        return filename

    def is_url_seen(self, url: str) -> bool:
        """Return True if the exact image URL has already been downloaded."""
        return url in self.seen_urls

    def is_hash_seen(self, sha256_hash: str) -> bool:
        """Return True if an image with this SHA-256 hash has already been stored."""
        return sha256_hash in self.seen_hashes

    def add_record(self, record: ImageMetadata) -> None:
        """Record a newly downloaded image and immediately persist to CSV and JSON."""
        self.records.append(record)
        if record.sha256_hash:
            self.seen_hashes.add(record.sha256_hash)
        if record.original_image_url:
            self.seen_urls.add(record.original_image_url)
        self.save()

    def save(self) -> None:
        """Save all collected metadata records to both CSV (via Pandas) and JSON."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.parent.mkdir(parents=True, exist_ok=True)

        rows = [r.to_dict() for r in self.records]
        df = pd.DataFrame(rows, columns=METADATA_COLUMNS)
        df.to_csv(self.csv_path, index=False, encoding="utf-8")

        self.json_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
