# Facebook Group Image Scraper & Food Filter

A cross-platform (macOS & Windows), lightweight pipeline to scrape images from Facebook Groups and filter authentic food imagery from promotional flyers, menus, and non-food media using zero-shot vision classification (TinyCLIP) with Apple Silicon Metal (MPS) and CUDA acceleration.

---

## Installation & Setup

### Prerequisites

- **macOS:** macOS 12 Monterey, 13 Ventura, 14 Sonoma, or 15 Sequoia (Apple Silicon M1/M2/M3/M4 or Intel).
  - Python 3.11+ (via Homebrew `brew install python@3.11` or official installer).
  - Xcode Command Line Tools (`xcode-select --install`).
- **Windows:** Windows 10/11 with Python 3.11+.

---

### 1. Create and Activate Virtual Environment

#### macOS / Linux (zsh or bash)
```bash
# Navigate to the scraper directory
cd scrapper

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

#### Windows (PowerShell)
```powershell
# Navigate to the scraper directory
cd scrapper

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

> **macOS Note on SSL Certificates:**
> If you installed Python using the official python.org macOS installer, run the certificates installation script once to prevent `SSL: CERTIFICATE_VERIFY_FAILED` errors:
> ```bash
> # Adjust Python version number to match yours:
> /Applications/Python\ 3.11/Install\ Certificates.command
> ```

---

### 2. Install Dependencies

Once the virtual environment is activated:

```bash
# Upgrade pip
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt
```

#### Optional: Make the script directly executable on macOS
```bash
chmod +x main.py
```

---

## Running the Scraper

### 1. Interactive Mode (Default)
Run without arguments to launch the guided interactive configuration wizard. Press **Enter** to accept default values:

**macOS:**
```bash
python3 main.py
# or directly if executable:
./main.py
```

**Windows:**
```powershell
python main.py
```

---

### 2. CLI / Headless Mode

Run directly from the terminal with command-line arguments:

#### macOS / Linux:
```bash
python3 main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --max-images 100 \
  --output-dir "facebook_group_dataset"
```

#### Windows (PowerShell):
```powershell
python main.py `
  --non-interactive `
  --url "https://www.facebook.com/groups/foodbloggersbd/media" `
  --max-images 100 `
  --output-dir "facebook_group_dataset"
```

---

### 3. Apple Silicon (M1/M2/M3/M4) Hardware Acceleration on macOS

The vision classifier automatically detects and leverages Apple Silicon's GPU via **Metal Performance Shaders (MPS)**:

```bash
# Verify Apple Silicon MPS support in your environment:
python3 -c "import torch; print('MPS available:', torch.backends.mps.is_available())"
```

To control hardware acceleration explicitly:
```bash
# Explicitly use Apple Silicon Metal (MPS):
python3 main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --device mps

# Force CPU inference (useful for Intel Macs or low memory):
python3 main.py \
  --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --device cpu
```

---

### 4. macOS Power & Background Execution Tips

- **Keep Mac Awake during Long Scrapes (`caffeinate`):**
  macOS includes a built-in `caffeinate` utility that prevents your Mac from sleeping while the script is active:
  ```bash
  caffeinate -i python3 main.py \
    --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --max-images 500
  ```

- **Run in the Background (Headless / Detached on macOS):**
  ```bash
  nohup python3 main.py \
    --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --max-images 500 > scraper_run.log 2>&1 &
  
  # Tail execution logs live:
  tail -f scraper_run.log
  ```

---

### 5. Common Scraping Examples

- **Extract single primary image per post (skip multi-image albums):**
  ```bash
  python3 main.py --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --single-image-only
  ```

- **Adjust delays for polite rate limiting:**
  ```bash
  python3 main.py --non-interactive \
    --url "https://www.facebook.com/groups/foodbloggersbd/media" \
    --post-delay 3.0 \
    --download-delay 1.5
  ```

- **Start fresh (ignore previously downloaded images):**
  ```bash
  python3 main.py --non-interactive \
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

To customize the confidence threshold (default is `0.50`):
```bash
python3 main.py --non-interactive \
  --url "https://www.facebook.com/groups/foodbloggersbd/media" \
  --food-threshold 0.60
```

### 2. Standalone Filter (Filter Existing Images)
Run the filter on an already downloaded dataset without re-scraping (useful for tuning thresholds or switching between CPU and MPS on Mac):

**macOS (with Apple Silicon Metal acceleration):**
```bash
python3 main.py \
  --filter-only \
  --output-dir "facebook_group_dataset" \
  --food-threshold 0.50 \
  --device mps
```

**Windows:**
```powershell
python main.py `
  --filter-only `
  --output-dir "facebook_group_dataset" `
  --food-threshold 0.50
```

> **Note**: `--filter-only` automatically inspects `images/`, `food_images/`, and `non_food_images/`, while safely ignoring macOS hidden files (`.DS_Store`, `._*`). You can re-run with different thresholds anytime without manually moving files back.

### 3. Disable Filtering (Raw Scrape Only)
Download images without running the vision model:
```bash
python3 main.py --non-interactive \
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
| `--device` | - | `str` | `auto` | Vision inference device: `auto`, `cpu`, `cuda`, `mps` (Apple Silicon Metal) |
| `--filter-only` | - | `flag` | `False` | Only run vision filter on existing output directory |
| `--food-threshold` | - | `float` | `0.50` | Confidence threshold (0.0–1.0) for food classification |
| `--filter-food` | - | `flag` | `True` | Run food classifier after scraping (default: enabled) |
| `--no-filter-food` | - | `flag` | `False` | Disable vision classification during scraping |
| `--post-delay` | - | `float` | `2.0` | Delay in seconds between post requests |
| `--download-delay` | - | `float` | `1.0` | Delay in seconds between image downloads |
| `--max-posts` | `-p` | `int` | `200` | Maximum number of group posts to inspect |
| `--single-image-only` | - | `flag` | `False` | Extract only the primary image from each post |
| `--timeout` | `-t` | `int` | `30` | HTTP request timeout in seconds |
| `--max-retries` | - | `int` | `3` | Maximum retry attempts for failed downloads |
| `--no-resume` | - | `flag` | `False` | Disable resuming from existing metadata |

---

## Output Files

After a run, the output directory contains:
- `food_images/`: Images confirmed as authentic food dishes.
- `non_food_images/`: Filtered-out media (flyers, text menus, selfies, packaging).
- `metadata/`: CSV and JSON files tracking image IDs, dimensions, file hashes, source URLs, and classification scores.
  - `food_images_metadata.csv` & `food_images_metadata.json`
  - `image_classifications.csv`
  - `food_classification_report.json`
  - `scraping_report.json`
- `logs/`: Application execution logs (`scraper.log`).

---

## macOS Troubleshooting

### 1. `zsh: permission denied: ./main.py`
Make the script executable:
```bash
chmod +x main.py
```
Or run explicitly with python3:
```bash
python3 main.py
```

### 2. `urllib.error.URLError: [SSL: CERTIFICATE_VERIFY_FAILED]`
Run the Python certificate installer provided with the macOS Python package:
```bash
# If using Python 3.11:
/Applications/Python\ 3.11/Install\ Certificates.command

# If using Python 3.12:
/Applications/Python\ 3.12/Install\ Certificates.command
```

### 3. AppleDouble / `.DS_Store` / `._*` files
The scraper and vision filter automatically ignore macOS hidden files and AppleDouble resource fork files (`.DS_Store`, `._*`) so they will not interfere with classification or cause dataset contamination.

### 4. Running Unit Tests
To verify test suite on macOS:
```bash
python3 -m unittest discover -s tests
```
