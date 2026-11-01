"""Facebook Group Gallery Image Scraper package."""

import warnings

warnings.filterwarnings("ignore", message=".*urllib3.*doesn't match a supported version.*")

from .config import ScraperConfig
from .cli import main, run_scraping_pipeline

__all__ = ["ScraperConfig", "main", "run_scraping_pipeline"]
__version__ = "1.0.0"

