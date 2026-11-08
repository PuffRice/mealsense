"""Inference architecture from the supplied Model.ipynb / Prototype.ipynb.

Keep layer names identical to the training model for strict checkpoint loading.
Only the dish head is used: component/ingredient heads were not supervised.
"""
import torch
from torch import nn
from torchvision.models import convnext_tiny


class SpatialAttention(nn.Module):
    def __init__(self, kernel_size=7):
        super().__init__()
        self.conv = nn.Conv2d(2, 1, kernel_size, padding=kernel_size // 2, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        avg_map = torch.mean(x, dim=1, keepdim=True)
        max_map = torch.max(x, dim=1, keepdim=True)[0]
        return x * self.sigmoid(self.conv(torch.cat([avg_map, max_map], dim=1)))


class BanglaFoodNet(nn.Module):
    def __init__(self, num_dishes, num_components=20, num_ingredients=50):
        super().__init__()
        # The supplied checkpoint contains all weights. Never download a backbone.
        self.backbone = convnext_tiny(weights=None).features
        self.attention = SpatialAttention()
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.dish_head = nn.Sequential(
            nn.Linear(768, 256), nn.GELU(), nn.Dropout(0.3), nn.Linear(256, num_dishes))
        self.component_head = nn.Sequential(
            nn.Linear(768, 128), nn.GELU(), nn.Dropout(0.3), nn.Linear(128, num_components))
        self.ingredient_head = nn.Sequential(
            nn.Linear(768, 256), nn.GELU(), nn.Dropout(0.3), nn.Linear(256, num_ingredients))

    def forward(self, x):
        features = self.pool(self.attention(self.backbone(x))).flatten(1)
        return {'dish': self.dish_head(features),
                'components': self.component_head(features),
                'ingredients': self.ingredient_head(features)}
