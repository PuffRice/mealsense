# BanglaFoodNet artifacts

Source: https://drive.google.com/drive/folders/1RAlqpooPVkkW7pqyaYGcKgKkDrG7Yvxr

Downloaded on 2026-11-08 to `backend/model_artifacts/banglafoodnet/` (ignored by Git).
The folder contains `Model.ipynb`, `Prototype.ipynb`, `MultiLabelModel.ipynb`,
`benchmark.ipynb`, `food_image_model_benchmark.ipynb`, and both checkpoints below.
The notebooks are references, not executable application dependencies.

| Checkpoint | Bytes | SHA-256 |
| --- | ---: | --- |
| banglafoodnet_finetuned.pth (selected) | 325420995 | b210a967ecc5c65fcd862c3d6ea41b00cc44ae02d5d6aa5495b74aa736a0cce9 |
| banglafoodnet_best.pth (frozen backbone baseline) | 115016895 | 33f2e52f87a1c564e0055c33bf06e63038c3597bfd022208ce70ed08172c6725 |

`Model.ipynb` defines the selected inference architecture; `Prototype.ipynb`
defines training and evaluation preprocessing. The architecture is ConvNeXt-Tiny
features, spatial attention (7×7), adaptive pooling, and separate dish (19),
component (20), and ingredient (50) heads. Only the dish head was supervised.
Inference resizes RGB images to the checkpoint's `img_size` (160×160), converts
to a tensor, and applies ImageNet normalization. There is no center crop.
The backend loads `model_state_dict` strictly with `weights_only=True`, using
`class_names` in checkpoint order; it never downloads pretrained weights.

Classes: bakorkhani, beguni, biriyani, chickpeas, egg_omlete, fuchka, haleem,
hilsha_fish, kabab, kacha_golla, kala_bhuna, khichuri, mashed_potato,
morog_polao, nehari, porota, roshgolla, roshmalai, yogurt.

The supplied notebook reports fine-tuned epoch 10, validation macro F1
0.6656396218582875. This is training provenance, not a new application evaluation.
The checkpoint provides food classification only; it supplies no nutrient values,
serving weights, allergen declarations, or reliable ingredient predictions.

The source folder does not establish redistribution rights. Checkpoints and
original notebooks stay outside Git; confirm applicable rights before distribution.
