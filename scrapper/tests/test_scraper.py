"""Unit tests for the Facebook Group Scraper package."""

import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from PIL import Image
import torch
from facebook_scraper import exceptions as fb_exceptions

from fb_group_scraper.config import ScraperConfig, build_arg_parser
from fb_group_scraper.downloader import ImageDownloader
from fb_group_scraper.food_filter import FoodImageClassifier
from fb_group_scraper.metadata import ImageMetadata, MetadataManager
from fb_group_scraper.reporter import format_duration, format_size
from fb_group_scraper.scraper import (
    FacebookGroupPostScraper,
    GroupAccessError,
    extract_images_from_post_dict,
    upgrade_fbcdn_url_resolution,
)
from fb_group_scraper.validator import parse_and_validate_group_url


class TestValidatorAndConfig(unittest.TestCase):
    def test_parse_valid_gallery_urls(self):
        url = "https://www.facebook.com/groups/foodbloggersbd/media"
        parsed = parse_and_validate_group_url(url)
        self.assertEqual(parsed.group_id, "foodbloggersbd")
        self.assertTrue(parsed.is_gallery_subpage)
        self.assertEqual(parsed.detected_subpath, "media")

    def test_parse_numeric_group_photos_url(self):
        url = "https://m.facebook.com/groups/123456789/photos"
        parsed = parse_and_validate_group_url(url)
        self.assertEqual(parsed.group_id, "123456789")
        self.assertTrue(parsed.is_gallery_subpage)

    def test_arg_parser_device_flag(self):
        parser = build_arg_parser()
        args = parser.parse_args(["--device", "mps", "--url", "https://www.facebook.com/groups/test/media"])
        self.assertEqual(args.device, "mps")

        args_default = parser.parse_args(["--url", "https://www.facebook.com/groups/test/media"])
        self.assertEqual(args_default.device, "auto")


class TestMacCompatibility(unittest.TestCase):
    def test_device_resolution(self):
        clf_cpu = FoodImageClassifier(device="cpu")
        self.assertEqual(clf_cpu._resolve_device(torch), "cpu")

        clf_auto = FoodImageClassifier(device="auto")
        auto_dev = clf_auto._resolve_device(torch)
        self.assertIn(auto_dev, ("cpu", "cuda", "mps"))

    def test_macos_hidden_and_appledouble_files_ignored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            img_dir = td / "images"
            img_dir.mkdir()

            (img_dir / ".DS_Store").write_bytes(b"\x00\x00")
            (img_dir / "._image_000001.jpg").write_bytes(b"\x00\x00")
            (img_dir / "image_000001.jpg").write_bytes(b"\xff\xd8\xff\xe0")

            mgr = MetadataManager(
                csv_path=td / "metadata" / "meta.csv",
                json_path=td / "metadata" / "meta.json",
                images_dir=img_dir,
                resume=True,
            )
            self.assertEqual(mgr._next_index, 2)
            self.assertEqual(mgr.allocate_filename("jpg"), "image_000002.jpg")


class TestDownloaderAndScraperUtils(unittest.TestCase):
    def test_upgrade_fbcdn_url_resolution_preserves_cdn_constraints(self):
        url = "https:\\/\\/scontent.fdac14-1.fna.fbcdn.net\\/v\\/t39.30808-6\\/sample.jpg?cstp=mx1080x1080&amp;ctp=p160x160"
        normalized = upgrade_fbcdn_url_resolution(url)
        self.assertEqual(
            normalized,
            "https://scontent.fdac14-1.fna.fbcdn.net/v/t39.30808-6/sample.jpg?cstp=mx1080x1080&ctp=p160x160",
        )

    def test_formatting_utilities(self):
        self.assertEqual(format_duration(65), "00:01:05")
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertIn("MB", format_size(1024 * 1024 * 5))

    def test_metadata_license_and_consent_gating(self):
        rec = ImageMetadata(
            filename="image_000001.jpg",
            original_image_url="https://example.com/1.jpg",
            post_id="1",
            post_url="https://example.com/post/1",
            post_caption="Biryani",
            group_id="test",
            download_timestamp="2026-11-14T00:00:00Z",
            width=200,
            height=200,
            file_size_bytes=1024,
            sha256_hash="abc",
        )
        self.assertFalse(rec.is_approved_for_dataset())
        rec.license = "CC-BY-4.0"
        rec.permission_evidence = "Contributor signed consent form #42"
        rec.consent_status = "approved"
        self.assertTrue(rec.is_approved_for_dataset())

    def test_scraper_halts_on_login_required_or_ban(self):
        cfg = ScraperConfig(group_url="https://www.facebook.com/groups/test", group_id="test", max_posts=5)
        scraper = FacebookGroupPostScraper(cfg)

        def raise_login(**_kwargs):
            raise fb_exceptions.LoginRequired("login required")

        with self.assertRaises(GroupAccessError):
            list(scraper.iter_group_posts(get_posts_fn=raise_login))

        def raise_ban(**_kwargs):
            raise fb_exceptions.TemporarilyBanned("rate limited")

        with self.assertRaises(GroupAccessError):
            list(scraper.iter_group_posts(get_posts_fn=raise_ban))

    def test_extract_images_from_post_dict(self):
        extracted = extract_images_from_post_dict(
            {
                "post_id": "99",
                "post_text": "Homemade Khichuri",
                "images": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
            },
            group_id="foodgroup",
        )
        self.assertEqual(extracted.post_id, "99")
        self.assertEqual(len(extracted.image_urls), 2)

    def test_image_downloader_validates_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            cfg = ScraperConfig(
                group_url="https://www.facebook.com/groups/test",
                group_id="test",
                output_dir=td,
                download_delay=0.0,
            )
            cfg.images_dir.mkdir(parents=True, exist_ok=True)
            mgr = MetadataManager(
                csv_path=cfg.metadata_dir / "meta.csv",
                json_path=cfg.metadata_dir / "meta.json",
                images_dir=cfg.images_dir,
                resume=False,
            )

            buf = io.BytesIO()
            Image.new("RGB", (64, 64), color=(120, 180, 90)).save(buf, format="JPEG")
            jpeg_bytes = buf.getvalue()

            session = MagicMock()
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {"Content-Type": "image/jpeg"}
            resp.iter_content.return_value = [jpeg_bytes]
            session.get.return_value = resp

            downloader = ImageDownloader(cfg, mgr, session=session)
            first = downloader.download_image("https://example.com/dish.jpg", "10", "https://example.com/p/10", "Dish")
            self.assertEqual(first.status, "downloaded")
            self.assertIsNotNone(first.metadata)
            self.assertEqual(first.metadata.consent_status, "pending_review")

            # Duplicate URL check
            dup = downloader.download_image("https://example.com/dish.jpg", "10", "https://example.com/p/10", "Dish")
            self.assertEqual(dup.status, "duplicate")

            # Duplicate SHA-256 check on different URL
            dup_hash = downloader.download_image("https://example.com/dish2.jpg", "11", "https://example.com/p/11", "Dish")
            self.assertEqual(dup_hash.status, "duplicate")


if __name__ == "__main__":
    unittest.main()
