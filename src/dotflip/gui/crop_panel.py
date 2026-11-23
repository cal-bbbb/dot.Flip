"""The shared image preview (center pane) and its crop controls (right-hand properties panel).

``CropCanvas`` is the preview: plain image normally, or — when ``interactive`` is on — a
draggable/resizable crop box with a dimmed overlay outside it. ``CropControls`` is the small
properties-panel widget (ratio presets, a 3x3 origin picker, a pixel-size readout) that drives
whatever ``CropCanvas`` it's given; it owns no canvas of its own, since the canvas lives centrally
and is shared with the rest of the window.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from .crop_geometry import anchor_box, apply_ratio, move_box, resize_box
from .theme import ACCENT, BG, BORDER, FILL_LIGHT

_CANVAS_MAX = 1400  # longest side of the cached on-screen thumbnail (ratio math uses the true source size)
_HANDLE = 9  # drawn handle size, px
_HANDLE_HIT = 10  # hit-test tolerance, px

_MIN_ZOOM = 0.1  # 10%
_MAX_ZOOM = 8.0  # 800%
_WHEEL_ZOOM_BASE = 1.0015  # per wheel-delta unit; ~1.2x per standard 120-unit notch
_STEP_ZOOM = 1.25  # per +/- button or keyboard shortcut press

# 3x3 anchor grid: fraction of the box trimmed from the left/top on each axis
_ANCHORS = [
    (0.0, 0.0), (0.5, 0.0), (1.0, 0.0),
    (0.0, 0.5), (0.5, 0.5), (1.0, 0.5),
    (0.0, 1.0), (0.5, 1.0), (1.0, 1.0),
]

_RATIOS = [("Freeform", None), ("1:1", 1.0), ("4:3", 4 / 3), ("3:2", 3 / 2), ("16:9", 16 / 9), ("9:16", 9 / 16)]

_CURSORS = {
    "nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor,
    "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor,
    "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
}


def load_preview(path: Path | None, max_side: int = _CANVAS_MAX) -> tuple:
    """Open ``path``, EXIF-correct it, and return (downscaled PIL image or None, true native size)."""
    if path is None:
        return None, (0, 0)
    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img) or img
        native_size = img.size
        img = img.convert("RGBA" if "A" in img.mode or img.mode == "P" else "RGB")
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return img, native_size
    except Exception:
        return None, (0, 0)


def _parse_ratio(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    sep = ":" if ":" in text else "/" if "/" in text else None
    try:
        a, b = text.split(sep, 1) if sep else (text, "1")
        w, h = float(a), float(b)
    except ValueError:
        return None
    return w / h if w > 0 and h > 0 else None


class CropCanvas(QWidget):
    """The image preview; shows a draggable/resizable crop box when ``interactive`` is set.

    Supports zooming (Ctrl+scroll, Ctrl +/-/0, or the floating :class:`ZoomBar`) independently
    of the crop box, which stays correctly aligned since both derive from :meth:`_image_rect`.
    """

    changed = Signal()
    zoomChanged = Signal(float)  # 1.0 == fit-to-window

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.interactive = False
        self._pixmap: QPixmap | None = None
        self._native_size = (0, 0)  # true source pixels; used for ratio-accurate drag math
        self._box = [0.1, 0.1, 0.9, 0.9]
        self.ratio: float | None = None
        self._drag = None  # (handle_or_"move", start_pos: QPointF, start_box: tuple)
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.zoom_bar = ZoomBar(self, self)
        self.zoom_bar.setVisible(False)
        self._position_zoom_bar()

    # ---- state ----------------------------------------------------------
    def set_image(self, pil_img: Image.Image | None, native_size: tuple) -> None:
        """Swap the previewed image without touching the box: one crop applies to the whole batch."""
        self._pixmap = QPixmap.fromImage(ImageQt(pil_img)) if pil_img is not None else None
        self._native_size = native_size if pil_img is not None else (0, 0)
        self._drag = None
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.zoom_bar.setVisible(self._pixmap is not None)
        self.zoom_bar.sync_from_canvas()
        self.update()
        self.changed.emit()
        self.zoomChanged.emit(self._zoom)

    def set_interactive(self, on: bool) -> None:
        if self.interactive == on:
            return
        self.interactive = on
        self._drag = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def native_size(self) -> tuple:
        return self._native_size

    def box(self) -> tuple:
        return tuple(self._box)

    def set_box(self, box: tuple) -> None:
        x0, y0, x1, y1 = box
        self._box = [min(max(x0, 0.0), 1.0), min(max(y0, 0.0), 1.0), min(max(x1, 0.0), 1.0), min(max(y1, 0.0), 1.0)]
        self.update()
        self.changed.emit()

    def set_ratio(self, ratio: float | None) -> None:
        self.ratio = ratio
        if ratio and self._native_size[0] and self._native_size[1]:
            self._box = list(apply_ratio(tuple(self._box), self._native_size, ratio))
        self.update()
        self.changed.emit()

    # ---- geometry ---------------------------------------------------------
    def _image_rect(self) -> QRectF:
        if self._pixmap is None or self._pixmap.isNull():
            return QRectF()
        iw, ih = self._pixmap.width(), self._pixmap.height()
        avail = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        if avail.width() <= 0 or avail.height() <= 0 or not iw or not ih:
            return QRectF()
        base_scale = min(avail.width() / iw, avail.height() / ih)
        scale = base_scale * self._zoom
        w, h = iw * scale, ih * scale
        cx = avail.center().x() + self._pan.x()
        cy = avail.center().y() + self._pan.y()
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    # ---- zoom ---------------------------------------------------------
    def zoom_percent(self) -> int:
        return round(self._zoom * 100)

    def set_zoom_percent(self, pct: float, anchor: QPointF | None = None) -> None:
        self._set_zoom(pct / 100, anchor)

    def reset_zoom(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self.update()
        self.zoomChanged.emit(self._zoom)

    def _set_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        zoom = min(max(zoom, _MIN_ZOOM), _MAX_ZOOM)
        if self._pixmap is None or abs(zoom - self._zoom) < 1e-6:
            return
        if anchor is None:
            anchor = QRectF(self.rect()).center()
        old_rect = self._image_rect()
        old_scale = old_rect.width() / self._pixmap.width() if old_rect.width() else 0
        if old_scale:
            img_x = (anchor.x() - old_rect.x()) / old_scale
            img_y = (anchor.y() - old_rect.y()) / old_scale
            self._zoom = zoom
            new_rect = self._image_rect()
            new_scale = new_rect.width() / self._pixmap.width()
            new_screen = QPointF(new_rect.x() + img_x * new_scale, new_rect.y() + img_y * new_scale)
            self._pan += anchor - new_screen
        else:
            self._zoom = zoom
        self.update()
        self.zoomChanged.emit(self._zoom)

    def _position_zoom_bar(self) -> None:
        margin = 10
        self.zoom_bar.move(self.width() - self.zoom_bar.width() - margin, self.height() - self.zoom_bar.height() - margin)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._position_zoom_bar()

    def wheelEvent(self, ev) -> None:
        if self._pixmap is not None and ev.modifiers() & Qt.ControlModifier:
            factor = _WHEEL_ZOOM_BASE ** ev.angleDelta().y()
            self._set_zoom(self._zoom * factor, ev.position())
            ev.accept()
            return
        super().wheelEvent(ev)

    def keyPressEvent(self, ev) -> None:
        if self._pixmap is not None and ev.modifiers() & Qt.ControlModifier:
            if ev.key() in (Qt.Key_Plus, Qt.Key_Equal):
                self._set_zoom(self._zoom * _STEP_ZOOM)
                return
            if ev.key() == Qt.Key_Minus:
                self._set_zoom(self._zoom / _STEP_ZOOM)
                return
            if ev.key() == Qt.Key_0:
                self.reset_zoom()
                return
        super().keyPressEvent(ev)

    def _box_rect(self) -> QRectF:
        r = self._image_rect()
        if r.isEmpty():
            return QRectF()
        x0, y0, x1, y1 = self._box
        return QRectF(r.x() + x0 * r.width(), r.y() + y0 * r.height(), (x1 - x0) * r.width(), (y1 - y0) * r.height())

    def _handle_points(self, box_rect: QRectF) -> dict:
        l, t, r, b = box_rect.left(), box_rect.top(), box_rect.right(), box_rect.bottom()
        cx, cy = (l + r) / 2, (t + b) / 2
        return {
            "nw": QPointF(l, t), "n": QPointF(cx, t), "ne": QPointF(r, t),
            "w": QPointF(l, cy), "e": QPointF(r, cy),
            "sw": QPointF(l, b), "s": QPointF(cx, b), "se": QPointF(r, b),
        }

    def _hit_handle(self, pos: QPointF) -> str | None:
        for name, pt in self._handle_points(self._box_rect()).items():
            if abs(pt.x() - pos.x()) <= _HANDLE_HIT and abs(pt.y() - pos.y()) <= _HANDLE_HIT:
                return name
        return None

    # ---- painting ----------------------------------------------------------
    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        img_rect = self._image_rect()
        if self._pixmap is None or img_rect.isEmpty():
            p.setPen(QColor(BORDER))
            p.drawText(self.rect(), Qt.AlignCenter, "Add files to preview.")
            p.end()
            return
        p.drawPixmap(img_rect, self._pixmap, QRectF(self._pixmap.rect()))
        if not self.interactive:
            p.end()
            return
        box_rect = self._box_rect()

        outer, inner = QPainterPath(), QPainterPath()
        outer.addRect(img_rect)
        inner.addRect(box_rect)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawPath(outer.subtracted(inner))

        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        for i in (1, 2):
            x = box_rect.x() + box_rect.width() * i / 3
            p.drawLine(QPointF(x, box_rect.top()), QPointF(x, box_rect.bottom()))
            y = box_rect.y() + box_rect.height() * i / 3
            p.drawLine(QPointF(box_rect.left(), y), QPointF(box_rect.right(), y))

        p.setPen(QPen(QColor(ACCENT), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(box_rect)

        p.setPen(QPen(QColor(ACCENT), 1))
        p.setBrush(QColor(FILL_LIGHT))
        for pt in self._handle_points(box_rect).values():
            p.drawRect(QRectF(pt.x() - _HANDLE / 2, pt.y() - _HANDLE / 2, _HANDLE, _HANDLE))
        p.end()

    # ---- mouse interaction -------------------------------------------------
    def mousePressEvent(self, ev) -> None:
        self.setFocus(Qt.MouseFocusReason)
        if not self.interactive or self._pixmap is None:
            return
        pos = ev.position()
        handle = self._hit_handle(pos)
        if handle:
            self._drag = (handle, pos, tuple(self._box))
        elif self._box_rect().contains(pos):
            self._drag = ("move", pos, tuple(self._box))

    def mouseMoveEvent(self, ev) -> None:
        if not self.interactive:
            return
        pos = ev.position()
        if self._drag is None:
            if self._pixmap is None:
                return
            handle = self._hit_handle(pos)
            if handle:
                self.setCursor(_CURSORS[handle])
            elif self._box_rect().contains(pos):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return
        kind, start_pos, start_box = self._drag
        img_rect = self._image_rect()
        if img_rect.width() <= 0 or img_rect.height() <= 0:
            return
        dx = (pos.x() - start_pos.x()) / img_rect.width()
        dy = (pos.y() - start_pos.y()) / img_rect.height()
        if kind == "move":
            self._box = list(move_box(start_box, dx, dy))
        else:
            self._box = list(resize_box(kind, start_box, dx, dy, self._native_size, self.ratio))
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, ev) -> None:
        self._drag = None

    def leaveEvent(self, ev) -> None:
        if self._drag is None:
            self.setCursor(Qt.ArrowCursor)


class ZoomBar(QWidget):
    """Floating [-  slider  +  pct%] control pinned to a canvas's bottom-right corner."""

    def __init__(self, canvas: CropCanvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._syncing = False
        self.setObjectName("zoomBar")
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(6)
        self.out_btn = QPushButton("−")
        self.out_btn.setProperty("role", "plain")
        self.out_btn.setFixedSize(20, 20)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(round(_MIN_ZOOM * 100), round(_MAX_ZOOM * 100))
        self.slider.setValue(100)
        self.slider.setFixedWidth(110)
        self.in_btn = QPushButton("+")
        self.in_btn.setProperty("role", "plain")
        self.in_btn.setFixedSize(20, 20)
        self.pct_label = QLabel("100%")
        self.pct_label.setFixedWidth(40)
        for w in (self.out_btn, self.slider, self.in_btn, self.pct_label):
            lay.addWidget(w)
        self.adjustSize()

        self.out_btn.clicked.connect(lambda: canvas.set_zoom_percent(max(canvas.zoom_percent() / _STEP_ZOOM, _MIN_ZOOM * 100)))
        self.in_btn.clicked.connect(lambda: canvas.set_zoom_percent(min(canvas.zoom_percent() * _STEP_ZOOM, _MAX_ZOOM * 100)))
        self.slider.valueChanged.connect(self._on_slider_changed)
        canvas.zoomChanged.connect(self._on_canvas_zoom_changed)

    def sync_from_canvas(self) -> None:
        self._on_canvas_zoom_changed(self._canvas.zoom_percent() / 100)

    def _on_slider_changed(self, value: int) -> None:
        if not self._syncing:
            self._canvas.set_zoom_percent(value)

    def _on_canvas_zoom_changed(self, zoom: float) -> None:
        pct = round(zoom * 100)
        self._syncing = True
        self.slider.setValue(max(self.slider.minimum(), min(self.slider.maximum(), pct)))
        self._syncing = False
        self.pct_label.setText(f"{pct}%")


class CropControls(QWidget):
    """Ratio presets, origin picker and size readout for a shared :class:`CropCanvas`."""

    def __init__(self, canvas: CropCanvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self._updating = False
        self.canvas.changed.connect(self._on_canvas_changed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._build_ratio_row())
        outer.addLayout(self._build_origin_row())
        outer.addLayout(self._build_size_rows())

        self._sync_origin_highlight()
        self._update_size_boxes()

    # ---- construction -------------------------------------------------
    def _build_ratio_row(self) -> QVBoxLayout:
        """A ratio-preset grid that wraps to a narrow properties column, 4 buttons per row."""
        col = QVBoxLayout()
        col.setSpacing(4)
        grid = QGridLayout()
        grid.setSpacing(4)
        self._ratio_group = QButtonGroup(self)
        self._ratio_group.setExclusive(True)
        self._ratio_values = {}
        per_row = 4
        for i, (label, value) in enumerate(_RATIOS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            self._ratio_group.addButton(btn, i)
            self._ratio_values[i] = value
            grid.addWidget(btn, i // per_row, i % per_row)
        self._custom_id = len(_RATIOS)
        self._custom_btn = QPushButton("Custom")
        self._custom_btn.setCheckable(True)
        self._custom_btn.setFixedHeight(26)
        self._ratio_group.addButton(self._custom_btn, self._custom_id)
        grid.addWidget(self._custom_btn, len(_RATIOS) // per_row, len(_RATIOS) % per_row)
        col.addLayout(grid)

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Custom ratio"))
        self.custom_ratio = QLineEdit()
        self.custom_ratio.setPlaceholderText("e.g. 5:7")
        self.custom_ratio.setEnabled(False)
        custom_row.addWidget(self.custom_ratio, 1)
        col.addLayout(custom_row)

        self._ratio_group.button(0).setChecked(True)  # Freeform
        self._ratio_group.idClicked.connect(self._ratio_selected)
        self.custom_ratio.returnPressed.connect(self._apply_custom_ratio)
        self.custom_ratio.editingFinished.connect(self._apply_custom_ratio)
        return col

    def _build_origin_row(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.addWidget(QLabel("Point of Origin:"))
        grid = QGridLayout()
        grid.setSpacing(2)
        self._origin_group = QButtonGroup(self)
        self._origin_group.setExclusive(True)
        for i, _ in enumerate(_ANCHORS):
            btn = QPushButton()
            btn.setProperty("role", "origin-cell")
            btn.setCheckable(True)
            btn.setFixedSize(20, 20)
            btn.setToolTip("Snap the crop box to this origin")
            self._origin_group.addButton(btn, i)
            grid.addWidget(btn, i // 3, i % 3)
        self._origin_group.idClicked.connect(self._origin_selected)
        col.addLayout(grid)
        return col

    def _build_size_rows(self) -> QFormLayout:
        form = QFormLayout()
        self.width_box = QSpinBox()
        self.width_box.setRange(1, 100_000)
        self.width_box.setSuffix(" px")
        self.height_box = QSpinBox()
        self.height_box.setRange(1, 100_000)
        self.height_box.setSuffix(" px")
        self.width_box.valueChanged.connect(self._on_width_changed)
        self.height_box.valueChanged.connect(self._on_height_changed)
        form.addRow("Width:", self.width_box)
        form.addRow("Height:", self.height_box)
        return form

    def _on_width_changed(self, value: int) -> None:
        if self._updating:
            return
        iw, _ih = self.canvas.native_size()
        if not iw:
            return
        x0, y0, x1, y1 = self.canvas.box()
        self.canvas.set_box((x0, y0, min(1.0, x0 + value / iw), y1))

    def _on_height_changed(self, value: int) -> None:
        if self._updating:
            return
        _iw, ih = self.canvas.native_size()
        if not ih:
            return
        x0, y0, x1, y1 = self.canvas.box()
        self.canvas.set_box((x0, y0, x1, min(1.0, y0 + value / ih)))

    # ---- crop spec ------------------------------------------------------
    def spec(self) -> tuple:
        return self.canvas.box()

    # ---- ratio ----------------------------------------------------------
    def _ratio_selected(self, id_: int) -> None:
        if id_ == self._custom_id:
            self.custom_ratio.setEnabled(True)
            self.custom_ratio.setFocus()
            self._apply_custom_ratio()
        else:
            self.custom_ratio.setEnabled(False)
            self.canvas.set_ratio(self._ratio_values[id_])

    def _apply_custom_ratio(self) -> None:
        if not self._custom_btn.isChecked():
            return
        ratio = _parse_ratio(self.custom_ratio.text())
        if ratio:
            self.canvas.set_ratio(ratio)

    # ---- origin -----------------------------------------------------------
    def _origin_selected(self, id_: int) -> None:
        ax, ay = _ANCHORS[id_]
        self.canvas.set_box(anchor_box(self.canvas.box(), ax, ay))

    def _sync_origin_highlight(self) -> None:
        x0, y0, x1, y1 = self.canvas.box()
        w, h = x1 - x0, y1 - y0
        matched = next(
            (i for i, (ax, ay) in enumerate(_ANCHORS) if abs((1 - w) * ax - x0) < 1e-3 and abs((1 - h) * ay - y0) < 1e-3),
            None,
        )
        self._origin_group.blockSignals(True)
        if matched is None:
            checked = self._origin_group.checkedButton()
            if checked:
                self._origin_group.setExclusive(False)
                checked.setChecked(False)
                self._origin_group.setExclusive(True)
        else:
            self._origin_group.button(matched).setChecked(True)
        self._origin_group.blockSignals(False)

    # ---- size fields ------------------------------------------------------
    def _update_size_boxes(self) -> None:
        iw, ih = self.canvas.native_size()
        if not iw:
            return
        x0, y0, x1, y1 = self.canvas.box()
        self._updating = True
        self.width_box.blockSignals(True)
        self.height_box.blockSignals(True)
        self.width_box.setValue(round((x1 - x0) * iw))
        self.height_box.setValue(round((y1 - y0) * ih))
        self.width_box.blockSignals(False)
        self.height_box.blockSignals(False)
        self._updating = False

    def _on_canvas_changed(self) -> None:
        self._sync_origin_highlight()
        self._update_size_boxes()
