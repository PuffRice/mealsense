# Facebook Group Gallery Image Scraper & Vision Dataset Pipeline

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Vision Model](https://img.shields.io/badge/Vision%20Classifier-TinyCLIP-orange.svg?logo=huggingface&logoColor=white)](https://huggingface.co/wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M)
[![Architecture](https://img.shields.io/badge/Architecture-Modular%20Pipeline-green.svg)](#system-architecture)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)](#license)

A high-performance, modular Python pipeline designed to scrape, validate, deduplicate, catalog, and filter images from Facebook Groups. Built for computer vision practitioners and dataset engineers, it combines robust HTTP scraping with zero-shot neural vision classification (Hugging Face TinyCLIP) to isolate authentic food imagery from promotional flyers, screenshots, and unrelated media.

---

## Key Highlights

- **Intelligent URL Resolution**: Validates Facebook Group Gallery URLs (`/media`, `/photos`, `/albums`) and resolves them into canonical group targets for reliable extraction.
- **Binary Integrity & Format Verification**: Inspects every downloaded image via Pillow, rejecting truncated files and saving files with verified MIME extensions (`.jpg`, `.png`, `.webp`, `.gif`).
- **Cryptographic Deduplication**: Generates SHA-256 digests for all images, preventing duplicate downloads across runs and sessions.
- **Zero-Shot Vision Food Classifier**: Incorporates an automated Hugging Face CLIP vision model (`TinyCLIP-ViT-8M`) to classify images into `food_images/` and `non_food_images/` with configurable confidence thresholds.
- **Incremental Metadata Persistence**: Continuously streams records to CSV and JSON formats after every download, guaranteeing zero data loss on unexpected exits.
- **Deterministic Session Resumability**: Seamlessly resumes interrupted tasks without re-downloading existing images or overwriting dataset files.
- **Interactive Wizard & Scriptable CLI**: Includes both an interactive console setup wizard and a comprehensive flag-driven CLI for headless automation.
- **Live Terminal Dashboard**: Displays real-time progress indicators, throughput statistics, and dataset summaries using `rich` and `tqdm`.

---

## System Architecture

```text
+-------------------------------------------------------------------------------+
|                             Scraper Execution Flow                            |
+-------------------------------------------------------------------------------+
                                        |
  [ Input Validation ]  -----> Parse Facebook Group Gallery URL & verify params
                                        |
  [ Post Ingestion ]    -----> Fetch group posts via m.facebook.com endpoint
                                        |
  [ Image Extraction ]  -----> Resolve high-resolution CDN media links
                                        |
  [ Download Engine ]   -----> Stream content, verify with Pillow, compute SHA-256
                                        |
  [ Metadata Persistence] ---> Incrementally write to CSV/JSON metadata records
                                        |
  [ Vision Filtration ] -----> TinyCLIP zero-shot classification (Food vs. Non-Food)
                                        |
  [ Reporting ]         -----> Output live terminal summaries and JSON reports
```

### Technical Note on `facebook-scraper` Mechanics
`facebook-scraper` is an HTTP parser targeting `https://m.facebook.com` rather than a browser automation engine (such as Selenium or Playwright).
- **Gallery Handling**: Facebook Group Gallery sub-paths (`/groups/<id>/media`) cannot be navigated as DOM gallery grids. The pipeline's validator extracts the group identifier and systematically scans posts via `get_posts(group=group_id)`.
- **Timing Differentiation**: **Post Delay (`--post-delay`)** controls rate-limiting between group post pagination requests, while **Download Delay (`--download-delay`)** throttles individual image file downloads from Facebook CDN servers (`scontent.xx.fbcdn.net`).
- **Access Compliance**: If Facebook restricts access (`LoginRequired` or `TemporarilyBanned`), the scraper halts gracefully, preserves all previously downloaded images and metadata, and generates an audit log.

---

## Directory Structure

```text
scrapper/
├── main.py                          # Top-level CLI entrypoint
├── requirements.txt                 # Application runtime dependencies
├── .gitignore                       # Production git ignore definitions
├── README.md                        # User and developer documentation
├── AGENT.md                         # Operational manual for autonomous AI agents
├── fb_group_scraper/                # Core modular application package
│   ├── __init__.py                  # Package exports
│   ├── cli.py                       # CLI parsing and pipeline orchestration
│   ├── config.py                    # ScraperConfig dataclass and interactive wizard
│   ├── downloader.py                # Resilient HTTP downloader & Pillow integrity checks
│   ├── food_filter.py               # TinyCLIP vision classifier for food dataset curation
│   ├── logger.py                    # Structured logging setup
│   ├── metadata.py                  # Incremental CSV/JSON metadata manager
│   ├── reporter.py                  # Rich live dashboard & final summary reports
│   ├── scraper.py                   # facebook-scraper post iterator wrapper
│   └── validator.py                 # URL, filesystem, and network validation
└── facebook_group_dataset/          # Generated output dataset directory
    ├── food_images/                 # Verified food imagery
    ├── non_food_images/             # Separated non-food imagery (flyers, menus, selfies)
    ├── logs/
    │   └── scraper.log              # Detailed execution log file
    └── metadata/
        ├── images_metadata.csv      # Complete metadata for all downloaded images
        ├── images_metadata.json     # JSON representation of all image metadata
        ├── food_images_metadata.csv # Filtered metadata for verified food images
        ├── food_images_metadata.json# JSON representation of food metadata
        ├── image_classifications.csv# Vision model confidence scores & predicted labels
        ├── food_classification_report.json # Classification summary and score distribution
        └── scraping_report.json     # Scraping run statistics, sizes, and duration
```

---

## Installation & Setup

### Prerequisites
- **Python 3.11+**
- Recommended: Dedicated virtual environment

### 1. Clone & Navigate to Repository
```bash
git clone <repository-url>
cd scrapper
```

### 2. Create and Activate Virtual Environment
```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Usage Guide

### 1. Interactive Wizard Mode (Default)
Run `main.py` without arguments to launch the guided interactive configuration wizard. Press **Enter** at any prompt to accept the sensible default:

```bash
python main.py
```

The wizard prompts for:
1. **Facebook Group Gallery URL** (default: `https://www.facebook.com/groups/foodbloggersbd/media`)
2. **Maximum number of images** (default: `100`)
3. **Gallery/page loading wait time** (`post_delay`, default: `2.0s`)
4. **Delay between image downloads** (`download_delay`, default: `1.0s`)
5. **Maximum number of posts to inspect** (default: `200`)
6. **Output directory** (default: `facebook_group_dataset`)
7. **Include multi-image gallery albums?** (default: `Yes`)
8. **HTTP request timeout** (default: `30s`)

---

### 2. Scripted & Headless Mode

Run headless tasks using command-line arguments:

```bash
python main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --max-images 100 \
  --post-delay 2.0 \
  --download-delay 1.0 \
  --max-posts 200 \
  --output-dir "facebook_group_dataset" \
  --timeout 30 \
  --food-threshold 0.50
```

#### Restrict to Single Primary Image per Post
```bash
python main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/examplegroup/media" \
  --single-image-only
```

#### Disable Vision Classification (Raw Scraping Only)
```bash
python main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/examplegroup/media" \
  --no-filter-food
```

---

### 3. Standalone Vision Classification Mode

To evaluate or re-classify an existing dataset without re-running the Facebook scraper (e.g., testing different confidence thresholds):

```bash
python main.py \
  --filter-only \
  --output-dir "facebook_group_dataset" \
  --food-threshold 0.55
```

> **Dynamic Re-Classification**: The classifier scans `images/`, `food_images/`, and `non_food_images/` concurrently, allowing you to re-run classification with different thresholds without manual directory resetting.

---

## Command-Line Arguments Reference

| Option | Flag | Type | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `--url` | `-u` | `str` | `None` | Facebook Group Gallery URL to scrape |
| `--max-images` | `-n` | `int` | `100` | Target maximum number of images to download |
| `--post-delay` | - | `float` | `2.0` | Delay in seconds between post pagination requests |
| `--download-delay` | - | `float` | `1.0` | Delay in seconds between individual image downloads |
| `--max-posts` | - | `int` | `200` | Maximum number of group posts to inspect |
| `--output-dir` | `-o` | `str` | `facebook_group_dataset` | Path to dataset output directory |
| `--single-image-only` | - | `flag` | `False` | Only extract the primary image from each post |
| `--timeout` | `-t` | `int` | `30` | HTTP request timeout in seconds |
| `--max-retries` | - | `int` | `3` | Maximum retry attempts for failed downloads |
| `--no-resume` | - | `flag` | `False` | Disables resuming from existing metadata |
| `--filter-food` | - | `flag` | `True` | Run neural vision model to separate food imagery |
| `--no-filter-food` | - | `flag` | `False` | Disable automated food image classification |
| `--filter-only` | - | `flag` | `False` | Run vision filter exclusively on existing dataset |
| `--food-threshold` | - | `float` | `0.50` | Confidence threshold (0.0–1.0) for food classification |
| `--non-interactive` | - | `flag` | `False` | Execute without interactive prompts (requires `--url`) |

---

## Dataset Schema & Output Specifications

### 1. `metadata/images_metadata.csv`
Tabular catalogue of all successfully ingested images:

| Column | Type | Example | Description |
| :--- | :---: | :--- | :--- |
| `image_id` | `str` | `image_000042` | Unique sequential identifier |
| `filename` | `str` | `image_000042.jpg` | Filename on local disk |
| `format` | `str` | `JPEG` | Image format verified by Pillow |
| `width` | `int` | `1080` | Image width in pixels |
| `height` | `int` | `1350` | Image height in pixels |
| `file_size_bytes` | `int` | `324611` | File size in bytes |
| `sha256` | `str` | `e3b0c44298fc...` | SHA-256 cryptographic digest |
| `url` | `str` | `https://scontent...` | Origin Facebook CDN URL |
| `post_id` | `str` | `1234567890` | Origin Facebook post identifier |
| `post_url` | `str` | `https://...` | Permlink to the source Facebook post |
| `download_timestamp` | `str` | `2026-11-01T07:50:12Z` | UTC ISO-8601 download timestamp |

### 2. `metadata/food_images_metadata.csv`
Contains records of all verified food images, including additional model outputs:
- `food_confidence`: Softmax probability score assigned by TinyCLIP.
- `filtered_path`: Relative location of the image (e.g. `food_images/image_000042.jpg`).

### 3. `metadata/scraping_report.json`
Comprehensive metadata report of scraping execution:
```json
{
  "group_url": "https://www.facebook.com/groups/foodbloggersbd/media",
  "group_id": "foodbloggersbd",
  "termination_reason": "Reached target image limit (100)",
  "total_posts_inspected": 118,
  "total_images_downloaded": 100,
  "duplicate_images": 30,
  "total_dataset_size_formatted": "36.58 MB",
  "average_image_dimensions": "1338.1 x 1679.3 px",
  "total_scraping_duration_formatted": "00:02:49"
}
```

---

## Vision Classification Engine

The food classification pipeline leverages **TinyCLIP** (`wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M`), a distilled Vision-Language Model that delivers zero-shot classification with minimal compute overhead (~30MB footprint).

### Classification Prompts
The model evaluates images against zero-shot candidate prompts:
- **Food Candidates**: Delicious food dishes, home-cooked meals, street food, plated desserts, culinary beverages.
- **Non-Food Candidates**: Text posters, price menus, promotional flyers, banners, selfies, landscapes, and closed retail packaging.

Images with aggregate food confidence exceeding `--food-threshold` (default: `0.50`) are organized into `food_images/`, while rejected media is archived in `non_food_images/`.

---

## Session Resumability & Robustness

- **Crash-Resistant State**: Records are flushed to `images_metadata.csv` and `images_metadata.json` immediately upon download completion.
- **Automatic Resume**: When pointed at an existing output directory, the scraper parses existing metadata and hashes, skips previously downloaded URLs and identical image content, and increments the filename index past the highest existing number (`image_XXXXXX`).
- **Binary Validation**: Pillow validates every byte stream before writing to disk, eliminating corrupt or truncated files.

---

## Developer and Agent Guidelines

For guidelines on programmatic interactions, model fine-tuning, or integrating with autonomous coding agents, refer to [`AGENT.md`](./AGENT.md).

---

## License

This project is licensed under the MIT License.
