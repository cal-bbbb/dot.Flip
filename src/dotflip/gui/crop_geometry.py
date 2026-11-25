"""Pure geometry for the interactive crop box: no Qt here, so the drag math is easy to unit-test.

A crop box is (x0, y0, x1, y1), each 0..1 and normalized to the *previewed* image's own
dimensions. Ratio-locked resizing needs real pixel dimensions (a ratio is a pixel-space concept),
so callers pass ``img_size`` alongside the normalized box.
"""
from __future__ import annotations

CORNERS = ("nw", "ne", "sw", "se")
EDGES = ("n", "s", "e", "w")
MIN_SIZE = 0.03  # smallest box dimension, as a fraction of the image


def move_box(start_box: tuple, dx: float, dy: float) -> tuple:
    """Translate the box by (dx, dy), clamped so it stays fully inside the image."""
    x0, y0, x1, y1 = start_box
    w, h = x1 - x0, y1 - y0
    nx0 = min(max(x0 + dx, 0.0), 1.0 - w)
    ny0 = min(max(y0 + dy, 0.0), 1.0 - h)
    return (nx0, ny0, nx0 + w, ny0 + h)


def anchor_box(box: tuple, ax: float, ay: float) -> tuple:
    """Reposition the box to the given anchor (0..1 per axis), keeping its current size."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    nx0 = (1 - w) * ax
    ny0 = (1 - h) * ay
    return (nx0, ny0, nx0 + w, ny0 + h)


def apply_ratio(box: tuple, img_size: tuple, ratio: float) -> tuple:
    """Reshape the box to ``ratio`` (width/height), keeping roughly the same area and center."""
    iw, ih = img_size
    x0, y0, x1, y1 = box
    cx_px, cy_px = (x0 + x1) / 2 * iw, (y0 + y1) / 2 * ih
    w_px, h_px = max((x1 - x0) * iw, 1.0), max((y1 - y0) * ih, 1.0)
    new_h = (w_px * h_px / ratio) ** 0.5
    new_w = new_h * ratio
    if new_w > iw:
        new_w, new_h = iw, iw / ratio
    if new_h > ih:
        new_h, new_w = ih, ih * ratio
    x0_px = min(max(cx_px - new_w / 2, 0.0), iw - new_w)
    y0_px = min(max(cy_px - new_h / 2, 0.0), ih - new_h)
    return (x0_px / iw, y0_px / ih, (x0_px + new_w) / iw, (y0_px + new_h) / ih)


def _resize_freeform(handle: str, start_box: tuple, dx: float, dy: float) -> tuple:
    x0, y0, x1, y1 = start_box
    if "w" in handle:
        x0 = min(max(x0 + dx, 0.0), x1 - MIN_SIZE)
    if "e" in handle:
        x1 = max(min(x1 + dx, 1.0), x0 + MIN_SIZE)
    if "n" in handle:
        y0 = min(max(y0 + dy, 0.0), y1 - MIN_SIZE)
    if "s" in handle:
        y1 = max(min(y1 + dy, 1.0), y0 + MIN_SIZE)
    return (x0, y0, x1, y1)


def _resize_ratio_corner(handle: str, start_box: tuple, dx: float, dy: float, img_size: tuple, ratio: float) -> tuple:
    iw, ih = img_size
    x0, y0, x1, y1 = start_box
    free_x, anchor_x = (x0, x1) if "w" in handle else (x1, x0)
    free_y, anchor_y = (y0, y1) if "n" in handle else (y1, y0)
    free_x, free_y = free_x + dx, free_y + dy
    ax_px, ay_px = anchor_x * iw, anchor_y * ih
    fx_px, fy_px = free_x * iw, free_y * ih
    sign_w = 1 if fx_px >= ax_px else -1
    sign_h = 1 if fy_px >= ay_px else -1
    avail_w = (iw - ax_px) if sign_w > 0 else ax_px
    avail_h = (ih - ay_px) if sign_h > 0 else ay_px
    mag_w = min(abs(fx_px - ax_px), avail_w)
    mag_h = min(abs(fy_px - ay_px), avail_h)
    # drive the resize from whichever axis the pointer moved further along, in ratio terms
    if mag_w / ratio >= mag_h:
        new_w = mag_w
        new_h = new_w / ratio
        if new_h > avail_h:
            new_h = avail_h
            new_w = new_h * ratio
    else:
        new_h = mag_h
        new_w = new_h * ratio
        if new_w > avail_w:
            new_w = avail_w
            new_h = new_w / ratio
    new_fx = (ax_px + sign_w * new_w) / iw
    new_fy = (ay_px + sign_h * new_h) / ih
    nx0, nx1 = sorted((anchor_x, new_fx))
    ny0, ny1 = sorted((anchor_y, new_fy))
    return (nx0, ny0, nx1, ny1)


def _resize_ratio_edge(handle: str, start_box: tuple, dx: float, dy: float, img_size: tuple, ratio: float) -> tuple:
    """Ratio-locked edge drag: resize about the opposite edge, staying centered on the other axis."""
    iw, ih = img_size
    x0, y0, x1, y1 = start_box
    cx_px, cy_px = (x0 + x1) / 2 * iw, (y0 + y1) / 2 * ih
    if handle in ("n", "s"):
        anchor_y, free_y = (y1, y0) if handle == "n" else (y0, y1)
        ay_px = anchor_y * ih
        fy_px = (free_y + dy) * ih
        sign_h = 1 if fy_px >= ay_px else -1
        avail_h = (ih - ay_px) if sign_h > 0 else ay_px
        new_h = min(abs(fy_px - ay_px), avail_h)
        new_w = new_h * ratio
        max_half_w = min(cx_px, iw - cx_px)
        if new_w / 2 > max_half_w:
            new_w = 2 * max_half_w
            new_h = new_w / ratio
        new_fy = (ay_px + sign_h * new_h) / ih
        ny0, ny1 = sorted((anchor_y, new_fy))
        return ((cx_px - new_w / 2) / iw, ny0, (cx_px + new_w / 2) / iw, ny1)
    anchor_x, free_x = (x1, x0) if handle == "w" else (x0, x1)
    ax_px = anchor_x * iw
    fx_px = (free_x + dx) * iw
    sign_w = 1 if fx_px >= ax_px else -1
    avail_w = (iw - ax_px) if sign_w > 0 else ax_px
    new_w = min(abs(fx_px - ax_px), avail_w)
    new_h = new_w / ratio
    max_half_h = min(cy_px, ih - cy_px)
    if new_h / 2 > max_half_h:
        new_h = 2 * max_half_h
        new_w = new_h * ratio
    new_fx = (ax_px + sign_w * new_w) / iw
    nx0, nx1 = sorted((anchor_x, new_fx))
    return (nx0, (cy_px - new_h / 2) / ih, nx1, (cy_px + new_h / 2) / ih)


def resize_box(handle: str, start_box: tuple, dx: float, dy: float, img_size: tuple, ratio: float | None) -> tuple:
    """Compute the new box for a handle drag. ``ratio`` None means freeform (unconstrained)."""
    if ratio is None:
        return _resize_freeform(handle, start_box, dx, dy)
    if handle in CORNERS:
        return _resize_ratio_corner(handle, start_box, dx, dy, img_size, ratio)
    return _resize_ratio_edge(handle, start_box, dx, dy, img_size, ratio)
