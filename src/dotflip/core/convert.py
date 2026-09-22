"""UI-free conversion engine used by the CLI, context menu and GUI."""
from __future__ import annotations

import io
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from .formats import Format, format_for_path, get_format

try:  # HEIC/HEIF reading; register once on import
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    pillow_heif = None

# Large but bounded; people convert big scans and panoramas.
Image.MAX_IMAGE_PIXELS = 500_000_000


class ConversionError(Exception):
    pass


@dataclass
class ConvertOptions:
    target: str = "png"
    format_options: dict = field(default_factory=dict)  # per-format overrides, see formats.Option
    # resize: None | ("percent", 50) | ("fit", (w, h))  (fit keeps aspect, never upscales)
    resize: tuple | None = None
    background: tuple = (255, 255, 255)  # used when flattening alpha
    keep_metadata: bool = True
    auto_orient: bool = True
    svg_width: int | None = None  # rasterize SVG at this width (None = intrinsic)
    svg_dpi: float = 96.0
    output_dir: Path | None = None  # None = next to source
    name_template: str = "{name}"
    collision: str = "rename"  # "rename" | "overwrite" | "skip"
    delete_original: bool = False


def _parse_sizes(text) -> list[tuple[int, int]]:
    sizes = []
    for part in str(text).split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= 256:
            sizes.append((int(part), int(part)))
    return sizes or [(256, 256)]


def _load(src: Path, fmt: Format | None, opts: ConvertOptions) -> Image.Image:
    if fmt and fmt.name == "svg":
        import resvg_py

        kwargs = {"svg_path": str(src), "dpi": opts.svg_dpi}
        if opts.svg_width:
            kwargs["width"] = opts.svg_width
        try:
            data = bytes(resvg_py.svg_to_bytes(**kwargs))
        except Exception as e:
            raise ConversionError(f"Could not render SVG: {e}") from e
        img = Image.open(io.BytesIO(data))
        img.load()
        return img
    try:
        return Image.open(src)
    except Exception as e:
        raise ConversionError(f"Could not open {src.name}: {e}") from e


def _resize(img: Image.Image, spec) -> Image.Image:
    if not spec:
        return img
    kind, val = spec
    w, h = img.size
    if kind == "percent":
        nw, nh = max(1, round(w * val / 100)), max(1, round(h * val / 100))
    elif kind == "fit":
        mw, mh = val
        scale = min((mw or w) / w, (mh or h) / h, 1.0)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    else:
        raise ConversionError(f"Unknown resize mode: {kind}")
    if (nw, nh) == (w, h):
        return img
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)


def _flatten(img: Image.Image, bg: tuple) -> Image.Image:
    if _has_alpha(img):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (*bg[:3], 255))
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")
    return img.convert("RGB")


def _prepare_frame(img: Image.Image, dst: Format, opts: ConvertOptions) -> Image.Image:
    img = _resize(img, opts.resize)
    if dst.name in ("jpeg", "bmp"):
        return _flatten(img, opts.background)
    if dst.name == "gif":
        return img.convert("RGBA") if _has_alpha(img) else img.convert("RGB")
    if dst.name == "ico" and img.width != img.height:  # icons are square: pad, don't stretch
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img.convert("RGBA"), ((side - img.width) // 2, (side - img.height) // 2))
        img = canvas
    if img.mode in ("CMYK", "YCbCr", "LAB", "HSV", "F"):
        return img.convert("RGB")
    if img.mode == "P":
        return img.convert("RGBA" if _has_alpha(img) else "RGB")
    if img.mode.startswith("I") and dst.name not in ("png", "tiff"):
        return img.point(lambda v: v / 256).convert("L") if img.mode != "I" else img.convert("L")
    return img


_SUB_IFD_TAGS = (0x8769, 0x8825, 0xA005)  # Exif, GPS, Interoperability pointers


def _flat_exif(exif: Image.Exif) -> Image.Exif:
    flat = Image.Exif()
    for tag, value in exif.items():
        if tag not in _SUB_IFD_TAGS:
            flat[tag] = value
    return flat


def _save_kwargs(dst: Format, opts: ConvertOptions) -> dict:
    o = {opt.key: opt.default for opt in dst.options}
    o.update(opts.format_options)
    n = dst.name
    if n == "jpeg":
        sub = {"4:4:4": 0, "4:2:2": 1, "4:2:0": 2}[o["subsampling"]]
        return dict(quality=int(o["quality"]), subsampling=sub, progressive=bool(o["progressive"]), optimize=True)
    if n == "png":
        return dict(compress_level=int(o["compress_level"]), optimize=bool(o["optimize"]))
    if n == "tiff":
        return dict(compression=o["compression"])
    if n == "gif":
        return dict(optimize=True)
    if n == "webp":
        return dict(quality=int(o["quality"]), lossless=bool(o["lossless"]))
    if n == "ico":
        return dict(sizes=_parse_sizes(o["sizes"]))
    if n == "avif":
        return dict(quality=int(o["quality"]), speed=int(o["speed"]))
    return {}


_reserve_lock = threading.Lock()
_reserved: set[Path] = set()  # outputs claimed by in-flight conversions (batch workers run concurrently)


def resolve_output(src: Path, dst: Format, opts: ConvertOptions) -> Path | None:
    """Pick the output path per collision policy. Returns None to skip."""
    folder = Path(opts.output_dir) if opts.output_dir else src.parent
    folder.mkdir(parents=True, exist_ok=True)
    stem = opts.name_template.format(name=src.stem, ext=src.suffix.lstrip("."))
    out = folder / f"{stem}{dst.extension}"
    with _reserve_lock:
        def free(p: Path) -> bool:
            return not p.exists() and p not in _reserved

        chosen: Path | None = None
        if free(out):
            chosen = out
        elif opts.collision == "overwrite" and out not in _reserved and out.resolve() != src.resolve():
            chosen = out  # never clobber the source with itself
        elif opts.collision == "skip":
            return None
        else:
            i = 1
            while not free(folder / f"{stem} ({i}){dst.extension}"):
                i += 1
            chosen = folder / f"{stem} ({i}){dst.extension}"
        _reserved.add(chosen)
        return chosen


def convert(src, opts: ConvertOptions | None = None) -> Path | None:
    """Convert one file. Returns the output path, or None if skipped."""
    opts = opts or ConvertOptions()
    src = Path(src)
    dst = get_format(opts.target)
    if not dst.writable:
        raise ConversionError(f"{dst.label} cannot be used as an output format")
    if not src.is_file():
        raise ConversionError(f"File not found: {src}")
    src_fmt = format_for_path(src)

    out = resolve_output(src, dst, opts)
    if out is None:
        return None

    img = None
    tmp = out.with_name(out.name + ".part")
    try:
        img = _load(src, src_fmt, opts)
        n_frames = getattr(img, "n_frames", 1)
        if opts.auto_orient and n_frames == 1:
            img = ImageOps.exif_transpose(img)

        save_kw = _save_kwargs(dst, opts)
        if opts.keep_metadata and dst.name in ("jpeg", "png", "tiff", "webp", "avif"):
            exif = img.getexif()
            if exif:
                exif.pop(0x0112, None)  # orientation already applied
                if dst.name == "tiff":
                    # libtiff can't write Exif/GPS/interop sub-IFD pointers ("Error setting from dictionary")
                    exif = _flat_exif(exif)
                save_kw["exif"] = exif.tobytes()
            icc = img.info.get("icc_profile")
            if icc:
                save_kw["icc_profile"] = icc

        try:
            if dst.animated and n_frames > 1 and src_fmt and src_fmt.animated:
                durations, frames = [], []
                for f in ImageSequence.Iterator(img):  # the iterator reuses one object, so copy per frame
                    durations.append(f.info.get("duration", 100))
                    frames.append(_prepare_frame(f.copy(), dst, opts))
                frames[0].save(
                    tmp, format=dst.pil_format, save_all=True, append_images=frames[1:],
                    duration=durations, loop=img.info.get("loop", 0), **save_kw,
                )
            else:
                img.seek(0)
                frame = _prepare_frame(img.copy() if n_frames > 1 else img, dst, opts)
                if dst.name == "gif":
                    colors = int(opts.format_options.get("colors", 256))
                    dither = Image.Dither.FLOYDSTEINBERG if opts.format_options.get("dither", True) else Image.Dither.NONE
                    frame = frame.convert("RGB").quantize(colors, dither=dither) if not _has_alpha(frame) else frame
                frame.save(tmp, format=dst.pil_format, **save_kw)
            os.replace(tmp, out)
        except Exception as e:
            raise ConversionError(f"Failed to write {dst.label}: {e}") from e
    finally:
        if img is not None:
            img.close()
        if tmp.exists():
            tmp.unlink()
        with _reserve_lock:
            _reserved.discard(out)

    if opts.delete_original and out.resolve() != src.resolve():
        src.unlink()
    return out
