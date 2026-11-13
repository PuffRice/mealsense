# DINOv3 dish classifier

The notebook `dinov3_integration/dinov3_training.ipynb` trained a frozen
DINOv3 ViT small backbone (12 layers, 384 hidden features, 6 heads, 16-pixel
patches, four register tokens) with a LayerNorm, Dropout(0.25), Linear
classification head. The head uses the CLS token and has nine outputs.
`checkpoint.pth` contains **all** backbone and head weights. It is a copy of
the original checkpoint; the ZIP export contains an identical checkpoint.
The checkpoint also contains the original class mapping, image size, and
validation macro F1 (0.87247). It contains no optimizer state or epoch.

Install `requirements.txt` and `requirements-local.txt` in `backend/`.
The latter includes PyTorch, torchvision, and Transformers 5.22.1.
No network access or pretrained download is used during inference.

Inference converts uploaded JPEG, PNG, or WebP images to RGB, resizes directly
to 224×224 with torchvision's default bilinear interpolation, converts to a
tensor, and normalizes with ImageNet mean/std. There is no crop. Softmax scores
rank nine known dishes; they are not calibrated probabilities, and there is no
validated rejection threshold for unrelated images. The model does not detect
multiple foods or estimate portions or nutrients.

Set `AI_PROVIDER=dinov3` in `backend/.env`. `AI_DINOV3_MODEL_DIR` defaults to
this directory, `AI_DINOV3_DEVICE` defaults to `auto` (CUDA if available,
otherwise CPU), and `AI_DINOV3_TOP_K` defaults to 5 (valid range 1–9).
The model loads lazily once per worker, then stays in evaluation mode.

Authenticated clients POST multipart `image` to `/api/v1/recognitions/`.
The existing response contains `status`, `candidates`, `model_version`, and
the saved recognition ID. Each candidate must be confirmed by the user before
logging. Example: `curl -b cookies.txt -F image=@dish.jpg
http://localhost:8000/api/v1/recognitions/`.

For direct prediction, from `backend/` run:

```python
from core.dinov3_recognition import predict_food
print(predict_food('dish.jpg', top_k=5))
```

Run `python manage.py test core.test_dinov3_recognition core.test_local_recognition`.
To replace the checkpoint, stop workers, replace only `checkpoint.pth` with a
checkpoint of the same architecture and class mapping, then restart. Strict
weight loading and mapping checks reject incompatible replacements.

Deployment artifacts belong outside public static and media directories.
The original training artifacts remain in `dinov3_integration/`.
