# Facebook Group Image Scraper & Food Filter

A lightweight pipeline to scrape images from Facebook and filter food imagery from promotional flyers, menus, and non-food media using zero-shot vision classification (TinyCLIP).

---

## Installation & Setup

### Prerequisites
- Python 3.11+

### 1. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Running the Scraper

### 1. Interactive Mode (Default)
Run without arguments to launch the guided configuration wizard. Press **Enter** to accept default values:
```bash
python main.py
```

### 2. CLI / Headless Mode
Run directly with command-line arguments:
```bash
python main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --max-images 100 \
  --output-dir "facebook_group_dataset"
```

#### Common Scraping Examples

- **Limit to single primary image per post (skip multi-image albums):**
  ```bash
  python main.py --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --single-image-only
  ```

- **Adjust delays for rate limiting:**
  ```bash
  python main.py --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --post-delay 3.0 \
    --download-delay 1.5
  ```

- **Start fresh (ignore previous runs):**
  ```bash
  python main.py --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --no-resume
  ```

---

## Filtering Food Images

The pipeline uses **TinyCLIP** (`wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M`) to classify images and separate authentic food photos from flyers, menus, selfies, and packaged products.

### 1. Automatic Filtering (Enabled by Default)
During standard scraping, the classifier runs automatically after downloading:
- Verified food images are moved to `food_images/`.
- Non-food media is moved to `non_food_images/`.
- Classification scores are saved to `metadata/image_classifications.csv` and `metadata/food_images_metadata.csv`.

To set a custom confidence threshold (default is `0.50`):
```bash
python main.py --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --food-threshold 0.60
```

### 2. Standalone Filter (Filter Existing Images)
Run the filter on an already downloaded dataset without scraping again (useful for tuning thresholds):
```bash
python main.py \
  --filter-only \
  --output-dir "facebook_group_dataset" \
  --food-threshold 0.50
```

> **Note**: `--filter-only` automatically inspects `images/`, `food_images/`, and `non_food_images/`, so you can re-run with different thresholds anytime without manually moving files back.

### 3. Disable Filtering (Raw Scrape Only)
Download images without running the vision model:
```bash
python main.py --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --no-filter-food
```

---

## CLI Options Reference

| Option | Flag | Type | Default | Description |
| :--- | :---: | :---: | :---: | :--- |
| `--url` | `-u` | `str` | `None` | Facebook Group Gallery URL to scrape |
| `--non-interactive` | - | `flag` | `False` | Run without prompts (requires `--url`) |
| `--max-images` | `-n` | `int` | `100` | Target maximum number of images to download |
| `--output-dir` | `-o` | `str` | `facebook_group_dataset` | Path to dataset output directory |
| `--filter-only` | - | `flag` | `False` | Only run vision filter on existing output directory |
| `--food-threshold` | - | `float` | `0.50` | Confidence threshold (0.0–1.0) for food classification |
| `--filter-food` | - | `flag` | `True` | Run food classifier after scraping (default: enabled) |
| `--no-filter-food` | - | `flag` | `False` | Disable vision classification during scraping |
| `--post-delay` | - | `float` | `2.0` | Delay in seconds between post requests |
| `--download-delay` | - | `float` | `1.0` | Delay in seconds between image downloads |
| `--max-posts` | - | `int` | `200` | Maximum number of group posts to inspect |
| `--single-image-only` | - | `flag` | `False` | Extract only the primary image from each post |
| `--timeout` | `-t` | `int` | `30` | HTTP request timeout in seconds |
| `--max-retries` | - | `int` | `3` | Maximum retry attempts for failed downloads |
| `--no-resume` | - | `flag` | `False` | Disable resuming from existing metadata |

---

## Output Files

After a run, the output directory contains:
- `food_images/`: Images confirmed as food dishes.
- `non_food_images/`: Filtered-out media (flyers, text menus, selfies, packaging).
- `metadata/`: CSV and JSON files tracking image IDs, dimensions, file hashes, source URLs, and classification scores.
- `logs/`: Application execution logs (`scraper.log`).
