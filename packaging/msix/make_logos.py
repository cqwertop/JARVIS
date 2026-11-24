"""Make the tile logos the MSIX package needs from packaging/assets/jarvis-256.png.

    python packaging/msix/make_logos.py <output folder>
"""
import sys
from pathlib import Path

from PIL import Image

src = Path(__file__).resolve().parent.parent / "assets" / "jarvis-256.png"
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

with Image.open(src) as img:
    img = img.convert("RGBA")
    for size, name in [(150, "Square150x150Logo.png"), (44, "Square44x44Logo.png"), (50, "StoreLogo.png")]:
        img.resize((size, size), Image.LANCZOS).save(out / name)
