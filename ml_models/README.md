# MealSense ML Models & Inference Pipeline (`ml_models/`)

This directory contains the unified machine-learning configuration, DINOv3 dish classifier inference service, fine-tuned Vision-Language Model (VLM) LoRA inference service, FCTB 2013 nutrition validation provider, and end-to-end food-to-nutrition pipeline for the **MealSense** Django backend.

---

## 1. Model Architecture Overview

### Stage 1: DINOv3 9-Class Dish Classifier (`ml_models/inference/classifier.py`)
- **Backbone:** Frozen `DINOv3 ViT-Small` (`dinov3_vit`, 12 layers, 384 hidden dimension, 6 attention heads, 16×16 patch size, 4 register tokens).
- **Classification Head:** `nn.Sequential(nn.LayerNorm(384), nn.Dropout(0.25), nn.Linear(384, 9))` operating on the CLS token (`last_hidden_state[:, 0]`).
- **Checkpoint:** `ml_models/classifier/dinov3_dish_best.pth` (86.48 MB, validation macro-F1 = `0.8725`). Contains both backbone and head weights (`state_dict`), class mapping (`dish_to_idx`), and `image_size` (`224`).
- **Preprocessing:** EXIF orientation transpose $\rightarrow$ RGB conversion $\rightarrow$ bilinear `Resize((224, 224))` $\rightarrow$ `ToTensor()` $\rightarrow$ ImageNet normalization (`mean=[0.485, 0.456, 0.406]`, `std=[0.229, 0.224, 0.225]`).
- **Supported Classes (9 Bangladeshi Dishes):**
  `bakorkhani`, `beguni`, `biriyani`, `chickpeas`, `egg_omlete`, `fuchka`, `haleem`, `hilsha_fish`, `kacchi`.

### Stage 2: Fine-Tuned VLM LoRA Adapter (`ml_models/inference/vlm.py`)
- **Base Model:** `HuggingFaceTB/SmolVLM-500M-Instruct` (`Idefics3ForConditionalGeneration` / `AutoModelForImageTextToText`, 517M parameters).
  - Local cache path: `D:\CS\Hackathon\Mealsense_Models\mealsense_local_artifacts\SmolVLM-500M-Instruct` (or automatically downloaded from Hugging Face Hub if absent).
- **Adapter Type:** PEFT `LORA` (`peft_version: 0.21.3`, `TaskType.CAUSAL_LM`, `r=16`, `lora_alpha=32`, `lora_dropout=0.05`).
- **Target Modules:** `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` (9.57M trainable parameters, 1.85% of total).
- **Processor & Tokenizer:** `Idefics3Processor` + `GPT2Tokenizer` (`vocab_size=49152`) with `do_image_splitting=False` and `longest_edge=384` (reducing vision tokens >10× for low-latency 8 GB VRAM inference).
- **Structured Output:** Generates strict JSON matching `VLMVisionOutputSchema` (`dish_matches_prediction`, `visual_fullness_multiplier`, `portion_confidence`, `visible_ingredients`, `observed_preparation_state`, `occluded_or_uncertain`).

### Stage 3: Grounded Nutrition Validation (`ml_models/inference/nutrition.py`)
- **Principle:** *AI identifies; the nutrition domain calculates.*
- Normalizes VLM-extracted visible ingredients and recipe-inferred ingredients (FAO/INFOODS Bangladeshi recipe priors) and queries verified per-100g edible composition records from **FCTB 2013 (Food Composition Table for Bangladesh, INFS, University of Dhaka)** (`fctb_2013_nutrition.db` + built-in verified table), applying raw-to-cooked yield factors (`cooking_yield_factor`).

---

## 2. VLM Checkpoint Inspection & Selection

Two checkpoint directories were inspected in `qwen_vlm_integration/` and `D:\CS\Hackathon\Mealsense_Models\ckpoint\`:

| Feature | `mealsense-vlm-lora` (Root) | `mealsense-vlm-lora/checkpoint-147` | `mealsense-qwen-vl-lora` |
| :--- | :--- | :--- | :--- |
| **Status** | Complete final export | Trainer step-147 snapshot | **Empty directory (0 files)** |
| **Base Model** | `HuggingFaceTB/SmolVLM-500M-Instruct` | `HuggingFaceTB/SmolVLM-500M-Instruct` | Untrained placeholder (`Qwen/Qwen2.5-VL-3B-Instruct` in base cache) |
| **Adapter Weights** | `adapter_model.safetensors` (38.35 MB, SHA256 `E333F6...`) | Identical `adapter_model.safetensors` (SHA256 `E333F6...`) | None |
| **Processor / Tokenizer Files** | **Included** (`processor_config.json`, `tokenizer.json`, `tokenizer_config.json`, `chat_template.jinja`) | **Not included** (contains trainer state `optimizer.pt`, `scheduler.pt`, `trainer_state.json`) | None |
| **Validation Loss** | `0.005374` (Epoch 3.0, Step 147, ~63 eval samples; teacher-forced JSON token loss only) | `0.005374` (Epoch 3.0, Step 147) | N/A |

> **Evaluation & Calibration Note:** `eval_loss: 0.005374` reflects next-token cross-entropy on the structured JSON validation split (~63 examples) and is **not** a calibrated benchmark of portion-weight accuracy (MAE/MAPE) or ingredient-recall F1 on an independent held-out test set. Portion weights and recipe-inferred ingredient ratios are approximate proposals that require user confirmation before logging.

### Recommended Checkpoint
- **`mealsense-vlm-lora` (default)** is recommended because it contains the best model weights (`load_best_model_at_end=True` at step 147) **plus** all required `Idefics3Processor` and tokenizer configuration files in the same directory.
- **`checkpoint-147`** is also fully supported via configurable checkpoint selection; when selected, `vlm.py` loads `adapter_model.safetensors` from `checkpoint-147` and automatically resolves the processor files from its parent directory (`mealsense-vlm-lora`).

### Switching Between Checkpoints
You can switch checkpoints without modifying code in any of three ways:
1. **Environment Variable:**
   ```powershell
   $env:AI_VLM_CHECKPOINT="checkpoint-147"
   # or
   $env:MEALSENSE_VLM_CHECKPOINT="mealsense-vlm-lora"
   ```
2. **YAML Configuration (`ml_models/configs/model_config.yaml`):**
   ```yaml
   vlm:
     selected_checkpoint: "checkpoint-147" # or "mealsense-vlm-lora"
   ```
3. **CLI Flag (`test_inference.py`):**
   ```powershell
   python ml_models/test_inference.py --image dish.jpg --checkpoint checkpoint-147
   ```

---

## 3. Hardware, GPU & CPU Configuration

Tested on local hardware (**NVIDIA GeForce RTX 5050, 8 GB VRAM, 16 GB RAM**):
- **VRAM Usage:** Loading both DINOv3 and `SmolVLM-500M-Instruct` + LoRA in `torch.bfloat16` uses only **~1.13 GB peak VRAM** out of 8 GB.
- **4-Bit Quantization:** Supported via `BitsAndBytesConfig` (`nf4`, double quantization) if `load_in_4bit: true` is enabled or when loading 2B/3B+ models on `<6.5 GB` free VRAM.
- **CPU Fallback:** Set `AI_DINOV3_DEVICE=cpu` and `AI_VLM_DEVICE=cpu` (or `--device cpu`) to run in `torch.float32` without a GPU.

---

## 4. Django API Integration

- **`POST /api/v1/recognitions/`**
  - Accepts authenticated multipart `image` uploads (`JPEG`, `PNG`, `WEBP` up to 8 MB / 20 MP).
  - Stores private image in `private_media/meal_images/` (`FoodImage`).
  - When `AI_PROVIDER=dinov3` (with `AI_VLM_ENABLED=1`) or `AI_PROVIDER=dinov3_vlm`, executes DINOv3 classification + VLM nutrition analysis and returns both backwards-compatible `candidates` and the full validated `analysis` object.
- **`GET /api/v1/recognitions/<uuid:pk>/`**
  - Retrieves the recognition session, candidate list, and structured `analysis` for the authenticated owner.
- **`POST /api/v1/recognitions/<uuid:pk>/`**
  - `{"action": "analyze", "checkpoint": "mealsense-vlm-lora"}`: Runs or refreshes the VLM nutrition analysis on an existing uploaded image.
  - `{"action": "save_meal", "meal_type": "lunch", "portion_weight_g": "350.00", "notes": "..."}`: Persists a `Meal` and ingredient-level `MealItem` records grounded in FCTB 2013 `Food` and `NutritionRecord` entries for the authenticated user.

---

## 5. Testing Commands

### Standalone CLI Inference Test (No Django Server Required)
```powershell
.\backend\.venv\Scripts\python.exe ml_models/test_inference.py --image test_food.jpg
.\backend\.venv\Scripts\python.exe ml_models/test_inference.py --image test_food.jpg --checkpoint checkpoint-147
```

### Automated Django & ML Test Suite
```powershell
cd backend
.\.venv\Scripts\python.exe manage.py test core
```

---

## 6. Common Errors & Troubleshooting

- **`ModuleNotFoundError: No module named 'torch'`**: Ensure `backend/.venv` includes `mealsense_ml.pth` or install `backend/requirements-local.txt`.
- ** PyTorch `+cpu` installed on a GPU machine**: Install CUDA wheels via `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128`.
- **`FileNotFoundError` on `mealsense-qwen-vl-lora`**: That directory was never populated during training; use `mealsense-vlm-lora` or `checkpoint-147`.
- **Disk Space Warnings on `D:\`**: `HF_HOME` and model paths are configured to use existing local artifacts without duplicating multi-gigabyte weights.
