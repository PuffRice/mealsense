#!/usr/bin/env python3
"""Top-level CLI runner for the Facebook Group Gallery Image Scraper."""

import sys
import warnings

warnings.filterwarnings("ignore", message=".*urllib3.*doesn't match a supported version.*")

from fb_group_scraper.cli import main

if __name__ == "__main__":
    sys.exit(main())

