"""Unit tests for the Facebook Group Scraper package."""

import tempfile
from pathlib import Path
import unittest

import torch

from fb_group_scraper.config import ScraperConfig, build_arg_parser
from fb_group_scraper.food_filter import FoodImageClassifier
from fb_group_scraper.metadata import ImageMetadata, MetadataManager
from fb_group_scraper.reporter import ScrapingStats, format_duration, format_size
from fb_group_scraper.scraper import upgrade_fbcdn_url_resolution
from fb_group_scraper.validator import parse_and_validate_group_url, validate_numeric_config


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
    def test_upgrade_fbcdn_url_resolution(self):
        url = "https://scontent.fdac14-1.fna.fbcdn.net/v/t39.30808-6/sample.jpg?cstp=mx1080x1080&ctp=p160x160&_nc_cat=1"
        upgraded = upgrade_fbcdn_url_resolution(url)
        self.assertNotIn("ctp=p160x160", upgraded)
        self.assertIn("cstp=mx1080x1080", upgraded)

    def test_formatting_utilities(self):
        self.assertEqual(format_duration(65), "00:01:05")
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertIn("MB", format_size(1024 * 1024 * 5))


if __name__ == "__main__":
    unittest.main()
