"""Draws the JARVIS icon and saves it in every format the installers need (.ico, .icns, .png).

    python packaging/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "assets"
BG, EDGE, MID, CYAN = (7, 17, 28, 255), (27, 58, 85, 255), (21, 64, 94, 255), (62, 224, 255, 255)


def draw(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.04
    d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=size * 0.22, fill=BG)
    c = size / 2
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - size * 0.2, c - size * 0.2, c + size * 0.2, c + size * 0.2), fill=(62, 224, 255, 110))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size * 0.06)))
    for r, color, w in ((0.36, EDGE, 0.03), (0.28, MID, 0.03), (0.2, CYAN, 0.035)):
        d.ellipse((c - size * r, c - size * r, c + size * r, c + size * r), outline=color, width=int(size * w))
    d.ellipse((c - size * 0.1, c - size * 0.1, c + size * 0.1, c + size * 0.1), fill=CYAN)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = draw()
    img.save(OUT / "jarvis.png")
    img.resize((256, 256), Image.LANCZOS).save(OUT / "jarvis-256.png")
    img.save(OUT / "jarvis.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(OUT / "jarvis.icns")
    # Inno Setup wizard images (left panel 164x314, small 55x58 at 100% scale; 2x versions for high-DPI screens).
    for name, (w, h) in {"wizard-large": (328, 628), "wizard-small": (110, 116)}.items():
        panel = Image.new("RGBA", (w, h), BG)
        icon = img.resize((int(min(w, h) * 0.8),) * 2, Image.LANCZOS)
        panel.alpha_composite(icon, ((w - icon.width) // 2, (h - icon.height) // 2))
        panel.convert("RGB").save(OUT / f"{name}.bmp")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
