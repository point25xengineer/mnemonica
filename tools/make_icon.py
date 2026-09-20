"""Build Mnemonica's .iconset from the source logo.

    python tools/make_icon.py assets/logo.png build/icon

Two things here are not obvious.

**The white ground is keyed out, not composited.** The source art is a mark on
white. Dropped straight onto the plate it shows as a white square inside the
rounded corners. The key uses a soft ramp rather than a threshold: a hard cut
sawtooths curved edges, and the ramp also lets white details *inside* the mark
— the bird's eye, the cursive m — read as the plate showing through, which is
the intended look rather than a hole.

**Small sizes are rendered separately, not resized down.** At 16px the drop
shadow is a grey smear, the plate shrinks to almost nothing against the
shadow's margin, and antialiasing bleeds any art near a corner straight
through the edge — which is what the bird's tail was doing. Apple ships
separate art per size for the same reason.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

WHITE_CLEAR = 246.0
"""Luminance at which the ground becomes fully transparent."""
WHITE_RAMP = 14.0
"""How far below that it takes to become fully opaque."""


def keyed(logo: pathlib.Path) -> Image.Image:
    src = Image.open(logo).convert("RGBA")
    a = np.asarray(src).astype(np.float32)
    lum = a[..., :3].min(axis=-1)
    a[..., 3] = np.clip((WHITE_CLEAR - lum) / WHITE_RAMP, 0.0, 1.0) * 255.0
    art = Image.fromarray(a.astype(np.uint8), "RGBA")
    return art.crop(art.getchannel("A").getbbox())


def render(art: Image.Image, *, canvas: int, plate: int, radius: int,
           pad: int, shadow: bool) -> Image.Image:
    inner = plate - pad * 2
    s = min(inner / art.width, inner / art.height)
    scaled = art.resize((max(1, round(art.width * s)),
                         max(1, round(art.height * s))), Image.LANCZOS)

    icon = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    box = ((canvas - plate) // 2,) * 2 + ((canvas + plate) // 2,) * 2

    if shadow:
        sh = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            (box[0], box[1] + 10, box[2], box[3] + 14),
            radius=radius, fill=(78, 68, 64, 66))
        icon.alpha_composite(sh.filter(ImageFilter.GaussianBlur(15)))

    plate_img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    ImageDraw.Draw(plate_img).rounded_rectangle(box, radius=radius,
                                                fill=(254, 253, 251, 255))
    icon.alpha_composite(plate_img)
    icon.alpha_composite(scaled, ((canvas - scaled.width) // 2,
                                  (canvas - scaled.height) // 2))
    return icon


def main(argv: list[str]) -> int:
    logo, out_dir = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    art = keyed(logo)

    big = render(art, canvas=1024, plate=824, radius=185, pad=104, shadow=True)
    small = render(art, canvas=1024, plate=968, radius=208, pad=132,
                   shadow=False)

    # 16 physical pixels is below what this mark survives. The tail is a thin
    # diagonal that antialiases to a smear and takes half the width with it,
    # leaving the head — the only part that says "bird" — three pixels wide.
    # So the smallest size gets the head and body alone: less information,
    # more of it legible. Apple ships simplified glyphs at this size for the
    # same reason.
    w, h = art.size
    body = art.crop((0, 0, int(w * 0.62), h))
    body = body.crop(body.getchannel("A").getbbox())
    tiny = render(body, canvas=1024, plate=940, radius=205, pad=170,
                  shadow=False)

    iconset = out_dir / "Mnemonica.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for stale in iconset.glob("*.png"):
        stale.unlink()

    for size in (16, 32, 128, 256, 512):
        for px, name in ((size, f"icon_{size}x{size}.png"),
                         (size * 2, f"icon_{size}x{size}@2x.png")):
            source = tiny if px <= 16 else small if px <= 64 else big
            source.resize((px, px), Image.LANCZOS).save(iconset / name)

    big.save(out_dir / "preview.png")
    print("  icon: 10 sizes (16px and 32-64px from separate art)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
