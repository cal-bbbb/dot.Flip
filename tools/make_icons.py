"""Generate the MSIX logo PNGs from assets/icon.png. Run: python tools/make_icons.py

assets/DotFlip.ico (app/installer icon) and assets/icon.png are the source artwork.
"""
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def main():
    src = Image.open(ASSETS / "icon.png").convert("RGBA")
    for name, size in (("StoreLogo.png", 50), ("Square44x44Logo.png", 44), ("Square150x150Logo.png", 150)):
        src.resize((size, size), Image.Resampling.LANCZOS).save(ASSETS / name)
    print("wrote MSIX logos")


if __name__ == "__main__":
    main()
