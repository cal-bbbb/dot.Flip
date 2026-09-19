from pathlib import Path

import pytest
from PIL import Image

from dotflip.core.batch import run_batch
from dotflip.core.convert import ConversionError, ConvertOptions, convert
from dotflip.core.formats import WRITABLE, get_format

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="red"/></svg>'


@pytest.fixture
def rgba(tmp_path) -> Path:
    p = tmp_path / "rgba.png"
    img = Image.new("RGBA", (64, 48), (0, 0, 255, 0))
    img.paste((255, 0, 0, 255), (0, 0, 32, 48))
    img.save(p)
    return p


@pytest.mark.parametrize("fmt", [f.name for f in WRITABLE])
def test_png_to_every_writable_format(rgba, fmt):
    out = convert(rgba, ConvertOptions(target=fmt, output_dir=rgba.parent / "out"))
    assert out.exists() and out.suffix == get_format(fmt).extension
    with Image.open(out) as im:
        assert im.format == get_format(fmt).pil_format


@pytest.mark.parametrize("src_fmt", ["jpeg", "gif", "webp", "bmp", "tiff", "avif", "ico"])
def test_roundtrip_back_to_png(rgba, src_fmt):
    mid = convert(rgba, ConvertOptions(target=src_fmt, output_dir=rgba.parent / "mid"))
    out = convert(mid, ConvertOptions(target="png", output_dir=rgba.parent / "back"))
    with Image.open(out) as im:
        assert im.format == "PNG"


def test_jpeg_flattens_transparency_onto_background(rgba):
    out = convert(rgba, ConvertOptions(target="jpeg", background=(0, 255, 0)))
    with Image.open(out) as im:
        assert im.mode == "RGB"
        r, g, b = im.getpixel((60, 40))
        assert g > 200 and r < 60


def test_jpeg_quality_affects_size(tmp_path):
    src = tmp_path / "noise.png"
    Image.effect_noise((200, 200), 60).convert("RGB").save(src)
    hi = convert(src, ConvertOptions(target="jpeg", format_options={"quality": 95}, name_template="hi"))
    lo = convert(src, ConvertOptions(target="jpeg", format_options={"quality": 10}, name_template="lo"))
    assert hi.stat().st_size > lo.stat().st_size


def test_collision_policies(rgba):
    a = convert(rgba, ConvertOptions(target="jpeg"))
    b = convert(rgba, ConvertOptions(target="jpeg"))
    assert a != b and b.name == "rgba (1).jpg"
    assert convert(rgba, ConvertOptions(target="jpeg", collision="skip")) is None
    assert convert(rgba, ConvertOptions(target="jpeg", collision="overwrite")) == a


def test_never_overwrites_source_with_itself(rgba):
    out = convert(rgba, ConvertOptions(target="png", collision="overwrite"))
    assert out != rgba and rgba.exists()


def test_delete_original(rgba):
    out = convert(rgba, ConvertOptions(target="webp", delete_original=True))
    assert out.exists() and not rgba.exists()


def test_resize_percent_and_fit(rgba):
    out = convert(rgba, ConvertOptions(target="png", resize=("percent", 50), name_template="half"))
    with Image.open(out) as im:
        assert im.size == (32, 24)
    out = convert(rgba, ConvertOptions(target="png", resize=("fit", (1000, 24)), name_template="fit"))
    with Image.open(out) as im:
        assert im.size == (32, 24)


def test_animated_gif_to_webp_keeps_frames(tmp_path):
    src = tmp_path / "a.gif"
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green", "blue")]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=80, loop=0)
    out = convert(src, ConvertOptions(target="webp"))
    with Image.open(out) as im:
        assert im.n_frames == 3


def test_animated_gif_to_png_uses_first_frame(tmp_path):
    src = tmp_path / "a.gif"
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green")]
    frames[0].save(src, save_all=True, append_images=frames[1:])
    out = convert(src, ConvertOptions(target="png"))
    with Image.open(out) as im:
        assert im.n_frames == 1


def test_cmyk_jpeg_to_png(tmp_path):
    src = tmp_path / "c.jpg"
    Image.new("CMYK", (10, 10), (0, 0, 0, 0)).save(src)
    out = convert(src, ConvertOptions(target="png"))
    with Image.open(out) as im:
        assert im.mode == "RGB"


def test_svg_input(tmp_path):
    src = tmp_path / "s.svg"
    src.write_text(SVG)
    out = convert(src, ConvertOptions(target="png", svg_width=80))
    with Image.open(out) as im:
        assert im.size[0] == 80


def test_ico_sizes(rgba):
    out = convert(rgba, ConvertOptions(target="ico", format_options={"sizes": "16,32"}))
    with Image.open(out) as im:
        assert set(im.info["sizes"]) == {(16, 16), (32, 32)}


def test_errors(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ConversionError):
        convert(bad, ConvertOptions(target="jpeg"))
    with pytest.raises(ConversionError):
        convert(tmp_path / "missing.png", ConvertOptions(target="jpeg"))
    with pytest.raises(ConversionError):
        convert(bad, ConvertOptions(target="svg"))
    assert not list(tmp_path.glob("*.part"))


def test_batch_isolates_failures(rgba, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"nope")
    results = run_batch([rgba, bad], ConvertOptions(target="webp"))
    assert results[0].ok and not results[1].ok


def test_batch_same_stem_different_sources_get_distinct_outputs(tmp_path):
    a, b = tmp_path / "x.png", tmp_path / "x.bmp"
    Image.new("RGB", (30, 30), "red").save(a)
    Image.new("RGB", (30, 30), "blue").save(b)
    for _ in range(20):  # repeat: the original bug was a race
        for f in tmp_path.glob("x*.tiff"):
            f.unlink()
        results = run_batch([a, b], ConvertOptions(target="tiff"), workers=4)
        assert all(r.ok for r in results), [r.error for r in results]
        assert results[0].output != results[1].output


@pytest.mark.parametrize("src_fmt", ["jpeg", "png", "webp", "avif"])
def test_exif_with_sub_ifd_converts_to_tiff(tmp_path, src_fmt):
    # Regression: EXIF sub-IFD pointers made libtiff fail with "Error setting from dictionary".
    exif = Image.Exif()
    exif[0x010F] = "Camera"
    exif.get_ifd(0x8769)[0x9003] = "2020:01:01 00:00:00"
    src = tmp_path / f"photo.{src_fmt}"
    Image.new("RGB", (64, 48), "red").save(src, exif=exif)
    out = convert(src, ConvertOptions(target="tiff", output_dir=tmp_path / "out"))
    with Image.open(out) as im:
        assert im.format == "TIFF"
