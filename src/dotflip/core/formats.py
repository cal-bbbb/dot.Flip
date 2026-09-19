"""Format registry: what we can read/write and which options each target exposes."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    kind: str  # "int" | "bool" | "choice" | "text"
    default: object
    min: int | None = None
    max: int | None = None
    choices: tuple = ()


@dataclass(frozen=True)
class Format:
    name: str  # canonical id, e.g. "jpeg"
    label: str
    extension: str  # primary extension incl. dot
    pil_format: str
    read_extensions: tuple
    writable: bool = True
    alpha: bool = True
    animated: bool = False
    options: tuple = field(default_factory=tuple)


_JPEG_OPTS = (
    Option("quality", "Quality", "int", 90, 1, 100),
    Option("subsampling", "Chroma subsampling", "choice", "4:2:0", choices=("4:4:4", "4:2:2", "4:2:0")),
    Option("progressive", "Progressive", "bool", False),
)

FORMATS: dict[str, Format] = {f.name: f for f in (
    Format("png", "PNG", ".png", "PNG", (".png",), options=(
        Option("compress_level", "Compression level", "int", 6, 0, 9),
        Option("optimize", "Optimize", "bool", False),
    )),
    Format("jpeg", "JPEG", ".jpg", "JPEG", (".jpg", ".jpeg", ".jpe", ".jfif"), alpha=False, options=_JPEG_OPTS),
    Format("tiff", "TIFF", ".tiff", "TIFF", (".tif", ".tiff"), options=(
        Option("compression", "Compression", "choice", "tiff_lzw", choices=("raw", "tiff_lzw", "tiff_adobe_deflate", "jpeg")),
    )),
    Format("gif", "GIF", ".gif", "GIF", (".gif",), animated=True, options=(
        Option("colors", "Colors", "int", 256, 2, 256),
        Option("dither", "Dither", "bool", True),
    )),
    Format("webp", "WebP", ".webp", "WEBP", (".webp",), animated=True, options=(
        Option("quality", "Quality", "int", 85, 1, 100),
        Option("lossless", "Lossless", "bool", False),
    )),
    Format("bmp", "BMP", ".bmp", "BMP", (".bmp", ".dib"), alpha=False),
    Format("ico", "ICO", ".ico", "ICO", (".ico",), options=(
        Option("sizes", "Sizes (comma-separated)", "text", "16,32,48,64,128,256"),
    )),
    Format("avif", "AVIF", ".avif", "AVIF", (".avif",), options=(
        Option("quality", "Quality", "int", 75, 0, 100),
        Option("speed", "Speed (0 slowest - 10 fastest)", "int", 6, 0, 10),
    )),
    Format("heic", "HEIC", ".heic", "HEIF", (".heic", ".heif"), writable=False),
    Format("svg", "SVG", ".svg", "SVG", (".svg",), writable=False),
)}

WRITABLE = [f for f in FORMATS.values() if f.writable]
READ_EXTENSIONS = sorted({e for f in FORMATS.values() for e in f.read_extensions})


def get_format(name: str) -> Format:
    key = name.lower().lstrip(".")
    key = {"jpg": "jpeg", "tif": "tiff", "heif": "heic"}.get(key, key)
    try:
        return FORMATS[key]
    except KeyError:
        raise ValueError(f"Unknown format: {name}") from None


def format_for_path(path) -> Format | None:
    ext = str(path).lower().rsplit(".", 1)
    ext = "." + ext[1] if len(ext) == 2 else ""
    for f in FORMATS.values():
        if ext in f.read_extensions:
            return f
    return None
