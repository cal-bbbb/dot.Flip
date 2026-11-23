import math

import pytest

from dotflip.gui.crop_geometry import anchor_box, apply_ratio, move_box, resize_box


def test_move_box_translates_and_clamps():
    assert move_box((0.2, 0.2, 0.4, 0.4), 0.1, 0.1) == pytest.approx((0.3, 0.3, 0.5, 0.5))
    assert move_box((0.2, 0.2, 0.4, 0.4), -1.0, -1.0) == pytest.approx((0.0, 0.0, 0.2, 0.2))
    assert move_box((0.2, 0.2, 0.4, 0.4), 1.0, 1.0) == pytest.approx((0.8, 0.8, 1.0, 1.0))


def test_anchor_box_keeps_size_moves_to_corner():
    box = anchor_box((0.1, 0.1, 0.3, 0.5), ax=1.0, ay=0.0)  # top-right, same 0.2 x 0.4 size
    assert box == pytest.approx((0.8, 0.0, 1.0, 0.4))


def test_apply_ratio_matches_requested_ratio_in_pixel_space():
    img_size = (1000, 400)
    box = apply_ratio((0.0, 0.0, 1.0, 1.0), img_size, ratio=1.0)  # square from a wide image
    w_px = (box[2] - box[0]) * img_size[0]
    h_px = (box[3] - box[1]) * img_size[1]
    assert w_px == pytest.approx(h_px, rel=1e-6)
    assert 0.0 <= box[0] and box[2] <= 1.0 and 0.0 <= box[1] and box[3] <= 1.0


def test_resize_freeform_corner_only_moves_its_own_edges():
    start = (0.2, 0.2, 0.6, 0.6)
    out = resize_box("se", start, dx=0.1, dy=-0.1, img_size=(100, 100), ratio=None)
    assert out == pytest.approx((0.2, 0.2, 0.7, 0.5))


def test_resize_freeform_respects_min_size_and_image_bounds():
    out = resize_box("se", (0.2, 0.2, 0.6, 0.6), dx=-10, dy=-10, img_size=(100, 100), ratio=None)
    assert out[2] - out[0] >= 0 and out[3] - out[1] >= 0
    out2 = resize_box("ne", (0.2, 0.2, 0.6, 0.6), dx=10, dy=-10, img_size=(100, 100), ratio=None)
    assert out2[2] <= 1.0 and out2[1] >= 0.0


@pytest.mark.parametrize("handle", ["nw", "ne", "sw", "se"])
def test_resize_ratio_corner_keeps_opposite_corner_fixed_and_matches_ratio(handle):
    start = (0.25, 0.25, 0.75, 0.75)  # square box in a square image
    img_size = (400, 400)
    ratio = 2.0  # wide rectangle
    out = resize_box(handle, start, dx=0.2, dy=0.2, img_size=img_size, ratio=ratio)
    x0, y0, x1, y1 = out
    w_px, h_px = (x1 - x0) * img_size[0], (y1 - y0) * img_size[1]
    assert w_px / h_px == pytest.approx(ratio, rel=1e-3)
    # the corner opposite the dragged one should not have moved
    opposite = {"nw": (x1, y1), "ne": (x0, y1), "sw": (x1, y0), "se": (x0, y0)}[handle]
    start_opposite = {
        "nw": (start[2], start[3]), "ne": (start[0], start[3]),
        "sw": (start[2], start[1]), "se": (start[0], start[1]),
    }[handle]
    assert opposite == pytest.approx(start_opposite, abs=1e-6)


def test_resize_ratio_corner_clamps_to_image_bounds():
    start = (0.4, 0.4, 0.6, 0.6)
    out = resize_box("se", start, dx=10, dy=10, img_size=(200, 100), ratio=1.0)
    x0, y0, x1, y1 = out
    assert x1 <= 1.0 and y1 <= 1.0
    w_px, h_px = (x1 - x0) * 200, (y1 - y0) * 100
    assert w_px == pytest.approx(h_px, rel=1e-3)


@pytest.mark.parametrize("handle", ["n", "s", "e", "w"])
def test_resize_ratio_edge_stays_centered_on_orthogonal_axis(handle):
    start = (0.25, 0.25, 0.75, 0.75)
    img_size = (300, 300)
    ratio = 1.5
    out = resize_box(handle, start, dx=-0.1 if handle == "w" else 0.1, dy=-0.1 if handle == "n" else 0.1,
                      img_size=img_size, ratio=ratio)
    x0, y0, x1, y1 = out
    w_px, h_px = (x1 - x0) * img_size[0], (y1 - y0) * img_size[1]
    assert w_px / h_px == pytest.approx(ratio, rel=1e-3)
    if handle in ("n", "s"):
        assert (x0 + x1) / 2 == pytest.approx((start[0] + start[2]) / 2, abs=1e-6)
    else:
        assert (y0 + y1) / 2 == pytest.approx((start[1] + start[3]) / 2, abs=1e-6)
