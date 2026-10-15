#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор иконки проекта: `assets/sketchfab-toolkit.ico`.

Рисуется один раз в большом размере и уменьшается с LANCZOS — так края
остаются гладкими во всех размерах иконы.

    python build/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "sketchfab-toolkit.ico"

SIZES = [16, 24, 32, 48, 64, 128, 256]
SUPERSAMPLE = 4
CANVAS = 1024

BACKGROUND_TOP = (16, 26, 38, 255)
BACKGROUND_BOTTOM = (9, 14, 22, 255)
EDGE = (56, 224, 216, 255)
EDGE_SOFT = (56, 224, 216, 90)


def _vertical_gradient(size: int) -> Image.Image:
    gradient = Image.new("RGBA", (1, size))
    for y in range(size):
        ratio = y / max(size - 1, 1)
        gradient.putpixel(
            (0, y),
            tuple(
                round(BACKGROUND_TOP[i] + (BACKGROUND_BOTTOM[i] - BACKGROUND_TOP[i]) * ratio)
                for i in range(4)
            ),
        )
    return gradient.resize((size, size))


def _rounded_mask(dim: int, radius_ratio: float = 0.22) -> Image.Image:
    mask = Image.new("L", (dim, dim), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, dim - 1, dim - 1), radius=round(dim * radius_ratio), fill=255
    )
    return mask


def _cube_points(cx: float, cy: float, radius: float) -> dict[str, tuple[float, float]]:
    """Вершины изометрического куба."""
    half_w = radius
    half_h = radius * 0.577  # 30°-проекция
    top = (cx, cy - radius)
    upper_left = (cx - half_w, cy - half_h)
    upper_right = (cx + half_w, cy - half_h)
    center = (cx, cy)
    lower_left = (cx - half_w, cy + half_h)
    lower_right = (cx + half_w, cy + half_h)
    bottom = (cx, cy + radius)
    return {
        "top": top,
        "upper_left": upper_left,
        "upper_right": upper_right,
        "center": center,
        "lower_left": lower_left,
        "lower_right": lower_right,
        "bottom": bottom,
    }


def render(dim: int = CANVAS) -> Image.Image:
    """Нарисовать иконку в разрешении `dim` (дальше она уменьшается до нужных размеров)."""
    points = _cube_points(dim / 2, dim / 2 + dim * 0.015, dim * 0.30)

    card = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    card.paste(_vertical_gradient(dim), (0, 0))
    card.putalpha(_rounded_mask(dim))

    layer = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # грани куба: лёгкая заливка + яркие рёбра
    draw.polygon(
        [points["top"], points["upper_right"], points["center"], points["upper_left"]],
        fill=(56, 224, 216, 46),
    )
    draw.polygon(
        [points["upper_left"], points["center"], points["bottom"], points["lower_left"]],
        fill=(56, 224, 216, 22),
    )
    draw.polygon(
        [points["upper_right"], points["lower_right"], points["bottom"], points["center"]],
        fill=(56, 224, 216, 34),
    )

    width = max(round(dim * 0.028), 1)
    outline = [
        (points["top"], points["upper_left"]),
        (points["top"], points["upper_right"]),
        (points["upper_left"], points["upper_right"]),
        (points["upper_left"], points["lower_left"]),
        (points["upper_right"], points["lower_right"]),
        (points["lower_left"], points["lower_right"]),
        (points["lower_left"], points["bottom"]),
        (points["lower_right"], points["bottom"]),
        (points["center"], points["bottom"]),
    ]
    for start, end in outline:
        draw.line([start, end], fill=EDGE, width=width, joint="curve")

    # блик сверху
    draw.line(
        [points["top"], points["center"]],
        fill=EDGE_SOFT,
        width=max(width // 2, 1),
    )

    card = Image.alpha_composite(card, layer)
    return card.resize((dim, dim), Image.LANCZOS)


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    base = render(CANVAS)
    icons = [base.resize((size, size), Image.LANCZOS) for size in SIZES]
    icons[-1].save(OUTPUT, format="ICO", sizes=[(s, s) for s in SIZES])

    preview = Path(__file__).resolve().parent / "icon-preview.png"
    base.resize((256, 256), Image.LANCZOS).save(preview)
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    print(f"wrote {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
