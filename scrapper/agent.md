# AGENT.md — Developer & AI Agent Operations Manual

> **Scope**: This document defines the architectural guidelines, system contracts, command workflows, and execution protocols for autonomous AI agents and engineers operating within or extending this repository.

---

## 1. System Overview & Core Mission

This repository contains a modular, production-ready **Facebook Group Gallery Image Scraper and Vision Dataset Curation Engine**. It extracts high-resolution images from Facebook Groups, validates binary and visual integrity, deduplicates content via SHA-256 cryptographic hashing, persists incremental metadata (CSV/JSON), supports session resumability, and automatically classifies/segregates images into **Food** vs. **Non-Food** subsets using a local zero-shot Hugging Face Vision-Language Model (`TinyCLIP`).

### Primary Objectives
1. **Ethical & Compliant Data Collection**: Operate using standard HTTP endpoints via `m.facebook.com` without bypassing authentication, spoofing credentials, or circumventing CAPTCHAs.
2. **Deterministic Resumability**: Ensure any scraping run can be terminated and resumed without re-downloading duplicate files or corrupting state.
3. **Automated Vision Filtration**: Apply multi-label zero-shot CLIP classification to isolate authentic food imagery from text flyers, menus, screenshots, and unrelated scenery.

---

## 2. Repository Layout & Module Directory

```text
scrapper/
├── main.py                          # Top-level CLI entrypoint script (executable)
├── pyproject.toml                   # Standard packaging metadata and dependencies
├── requirements.txt                 # Application runtime dependencies
├── .gitignore                       # Git exclusion rules (caches, virtual envs, OS artifacts)
├── README.md                        # User and developer documentation (macOS & Windows)
├── AGENT.md                         # This operational specifications manual
├── tests/                           # Unit test suite
│   └── test_scraper.py              # Validation, device resolution, and compatibility tests
├── fb_group_scraper/                # Core Python package
│   ├── __init__.py                  # Package initialization and exports
│   ├── cli.py                       # CLI parsing, interactive wizard & pipeline orchestration
│   ├── config.py                    # ScraperConfig dataclass, CLI flags & interactive prompts
│   ├── downloader.py                # Resilient HTTP downloader, Pillow check & SHA-256 hasher
│   ├── food_filter.py               # Hugging Face TinyCLIP food vs. non-food vision classifier
│   ├── logger.py                    # File and console logging configuration
│   ├── metadata.py                  # Incremental CSV/JSON persistence & session resume state
│   ├── reporter.py                  # Terminal live dashboard (Rich/tqdm) & final JSON reporter
│   ├── scraper.py                   # facebook-scraper wrapper & post image URL extraction
│   └── validator.py                 # URL parsing, filesystem permission & network checks
└── facebook_group_dataset/          # Default output dataset directory
    ├── food_images/                 # Verified food images (e.g. image_000001.jpg)
    ├── non_food_images/             # Filtered non-food images (text flyers, selfies, menus)
    ├── logs/
    │   └── scraper.log              # Detailed execution logs
    └── metadata/
        ├── images_metadata.csv      # Complete metadata for all downloaded images
        ├── images_metadata.json     # JSON mirror of images metadata
        ├── food_images_metadata.csv # Filtered metadata for food images only
        ├── food_images_metadata.json# JSON mirror of food metadata
        ├── image_classifications.csv# CLIP confidence scores and predicted class labels
        ├── food_classification_report.json # Summary metrics of vision classification run
        └── scraping_report.json     # Comprehensive scraping run summary & throughput stats
```

---

## 3. Architecture & Data Flow

```
                           +----------------------------------+
                           | User Input / CLI Flags / Wizard  |
                           +----------------------------------+
                                            |
                                            v
                           +----------------------------------+
                           |  Validator & Config Preparation   |
                           |  (URL parsing, Group ID, paths)  |
                           +----------------------------------+
                                            |
                                            v
                           +----------------------------------+
                           |     Scraper Engine (Posts)       |
                           |  facebook_scraper.get_posts()    |
                           +----------------------------------+
                                            |
                         Post dictionaries with image URLs
                                            v
                           +----------------------------------+
                           |    Downloader & Deduplication    |
                           |  - Requests stream + backoff     |
                           |  - Pillow binary format verify   |
                           |  - SHA-256 hash deduplication    |
                           +----------------------------------+
                                            |
                             image_XXXXXX.<ext> saved
                                            v
                           +----------------------------------+
                           |    MetadataManager Persistence   |
                           |  - Append to CSV/JSON metadata   |
                           |  - Track seen URLs & hashes      |
                           +----------------------------------+
                                            |
                                            v
                           +----------------------------------+
                           |    Vision Food Filter (CLIP)     |
                           |  - TinyCLIP zero-shot inference  |
                           |  - food_images/ vs non_food/     |
                           |  - food_images_metadata.csv/json |
                           +----------------------------------+
                                            |
                                            v
                           +----------------------------------+
                           |  Final Reports & Rich Dashboard  |
                           +----------------------------------+
```

---

## 4. Agent Operations & CLI Playbook

Agents invoking or scripting this pipeline MUST utilize the CLI interface provided by `main.py`.

### Common Invocations

#### A. Headless Scraping & Food Filtering (Standard Pipeline)
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

#### B. Standalone Vision Classification (Offline Re-filtering)
When images have already been downloaded into an output directory and only re-classification or threshold adjustments are required:
```bash
python main.py \
  --filter-only \
  --output-dir "facebook_group_dataset" \
  --food-threshold 0.55
```
*Note: The classifier automatically evaluates images across `images/`, `food_images/`, and `non_food_images/`, allowing seamless threshold re-tuning without manual directory flattening.*

#### C. Scraping Without Vision Filtration
To download images into `images/` without running the neural classifier:
```bash
python main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/examplegroup/media" \
  --no-filter-food \
  --max-images 50
```

#### D. Single Primary Image per Post Only
To ignore multi-image album carousels and extract only the primary post image:
```bash
python main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/examplegroup/media" \
  --single-image-only
```

---

## 5. Dataset Schema & Metadata Contracts

### `images_metadata.csv` & `images_metadata.json`
Every successfully downloaded, validated image receives a record with the following schema:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `image_id` | `str` | Canonical sequential ID (e.g. `image_000042`) |
| `filename` | `str` | Base filename on disk (e.g. `image_000042.jpg`) |
| `format` | `str` | Verified image format detected by Pillow (`JPEG`, `PNG`, `WEBP`, `GIF`) |
| `width` | `int` | Width in pixels |
| `height` | `int` | Height in pixels |
| `file_size_bytes` | `int` | Exact size on disk in bytes |
| `sha256` | `str` | 64-character lowercase SHA-256 cryptographic digest of the image bytes |
| `url` | `str` | Source Facebook CDN URL (`scontent.xx.fbcdn.net`) |
| `post_id` | `str` | Facebook post ID associated with the image |
| `post_url` | `str` | Canonical permalink URL to the Facebook post |
| `download_timestamp` | `str` | UTC ISO-8601 timestamp of download completion |

### `food_images_metadata.csv` & `food_images_metadata.json`
Contains all columns from `images_metadata.csv` for food-verified items, plus:
- `food_confidence` (`float`): Zero-shot probability score (0.0 to 1.0) assigned by CLIP.
- `filtered_path` (`str`): Relative path inside dataset (e.g. `food_images/image_000042.jpg`).

### `image_classifications.csv`
Records every classification prediction:
- `filename`: Base image name.
- `is_food`: Boolean outcome based on `food_confidence >= threshold`.
- `food_confidence`: Aggregated food prompt probability.
- `text_poster_confidence`: Aggregated promotional flyer / text meme probability.
- `other_non_food_confidence`: Aggregated person / scenery / background probability.
- `predicted_label`: Label category (`food`, `text_poster`, or `non_food_object`).
- `destination_path`: Relative target path (`food_images/...` or `non_food_images/...`).

---

## 6. Critical Technical Constraints & Guardrails

1. **facebook-scraper Architecture**:
   - `facebook-scraper` is an HTTP parser targeting `m.facebook.com`, **not** a JavaScript browser engine (like Playwright or Selenium).
   - Direct Facebook Group gallery sub-paths (`/media`, `/photos`) cannot be queried as standalone gallery grids by `facebook-scraper`. The validator normalizes gallery URLs and extracts the canonical `group_id`, then queries `get_posts(group=group_id)`.
   - `post_delay` controls polite delay between pagination requests; `download_delay` controls delay between CDN file fetches.

2. **Zero-Bypass Policy**:
   - Under no circumstances should agents implement automated login bypass, proxy rotation chains, or CAPTCHA solving.
   - When Facebook restricts access (triggering `LoginRequired` or `TemporarilyBanned`), `fb_group_scraper.scraper` catches this cleanly, logs the event, terminates scraping, saves all collected records, and exits with a detailed report.

3. **Incremental Persistence & Crash Recovery**:
   - Every file download is flushed to disk and metadata structures immediately.
   - Before downloading, `MetadataManager` checks if `url` or `sha256` has already been ingested.
   - Filename indexing (`_next_index`) scans `images/`, `food_images/`, and `non_food_images/` so resumed sessions never overwrite existing files.

4. **Model Caching & Cross-Platform (macOS & Windows) Portability**:
   - The vision classifier uses `wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M`, an ultra-lightweight (~30MB) CLIP model that downloads automatically on first run via Hugging Face Hub.
   - `HF_HUB_DISABLE_SYMLINKS_WARNING=1` is preset to prevent Windows symlink warnings.
   - On macOS with Apple Silicon (M1/M2/M3/M4), the classifier automatically supports Apple Metal Performance Shaders (`mps`) hardware acceleration via `--device mps` or default `--device auto`.
   - Hidden files and AppleDouble metadata (`.DS_Store`, `._*`) are automatically ignored across dataset directory scans to prevent corruption or Pillow read errors on macOS.
   - Handles `SIGTERM` and `SIGINT` signals gracefully to flush all metadata before process termination.

---

## 7. Extending & Modifying Code

When modifying this repository:
- **Preserve Docstrings & Typing**: All functions use PEP 484 type annotations and descriptive docstrings.
- **Maintain Clean Working Tree**: Do not commit `.pyc` files, `__pycache__` directories, or temporary scratch files.
- **Verify Execution**: Ensure `python main.py --help` and unit tests (`python -m unittest discover -s tests`) execute cleanly without syntax errors or unhandled exceptions.
