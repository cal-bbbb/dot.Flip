"""Custom title bar replacing the native one: [icon | menu bar | stretch | min/max/close].

Used with a frameless QMainWindow. Window move/maximize is handled here (drag or double-click
the empty strip); edge-resize is handled separately by :class:`ResizableRoot`, since this bar
only covers the top strip. The caption icons are hand-drawn (QPainter), not unicode glyphs, for
the same reliability reason as the hamburger icon.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenuBar, QPushButton, QVBoxLayout, QWidget

from .theme import BG, BORDER, TEXT
from .widgets import HEADER_HEIGHT

_BTN_WIDTH = 42
_RESIZE_MARGIN = 5

_EDGE_CURSORS = {
    frozenset({Qt.Edge.LeftEdge}): Qt.SizeHorCursor,
    frozenset({Qt.Edge.RightEdge}): Qt.SizeHorCursor,
    frozenset({Qt.Edge.TopEdge}): Qt.SizeVerCursor,
    frozenset({Qt.Edge.BottomEdge}): Qt.SizeVerCursor,
    frozenset({Qt.Edge.TopEdge, Qt.Edge.LeftEdge}): Qt.SizeFDiagCursor,
    frozenset({Qt.Edge.BottomEdge, Qt.Edge.RightEdge}): Qt.SizeFDiagCursor,
    frozenset({Qt.Edge.TopEdge, Qt.Edge.RightEdge}): Qt.SizeBDiagCursor,
    frozenset({Qt.Edge.BottomEdge, Qt.Edge.LeftEdge}): Qt.SizeBDiagCursor,
}


class ResizableRoot(QWidget):
    """Central widget for a frameless window: a small inset margin that drives edge-resize.

    Child content is laid out inside the margin (via :meth:`content_layout`), so nothing else
    occupies the margin strip and this widget reliably receives the mouse events there — a plain
    mouse-position check on the top-level window itself would be shadowed by whatever child
    widget fills that pixel.
    """

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setObjectName("resizableRoot")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(_RESIZE_MARGIN, _RESIZE_MARGIN, _RESIZE_MARGIN, _RESIZE_MARGIN)
        outer.setSpacing(0)
        self._content = QVBoxLayout()
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(0)
        outer.addLayout(self._content)

    def content_layout(self) -> QVBoxLayout:
        return self._content

    def _edges_at(self, pos: QPoint) -> set:
        x, y, w, h, m = pos.x(), pos.y(), self.width(), self.height(), _RESIZE_MARGIN
        edges = set()
        if x <= m:
            edges.add(Qt.Edge.LeftEdge)
        elif x >= w - m:
            edges.add(Qt.Edge.RightEdge)
        if y <= m:
            edges.add(Qt.Edge.TopEdge)
        elif y >= h - m:
            edges.add(Qt.Edge.BottomEdge)
        return edges

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and not self._window.isMaximized():
            edges = self._edges_at(ev.position().toPoint())
            if edges:
                handle = self._window.windowHandle()
                if handle is not None:
                    combined = Qt.Edges()
                    for e in edges:
                        combined |= e
                    handle.startSystemResize(combined)
                    return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if not self._window.isMaximized():
            edges = self._edges_at(ev.position().toPoint())
            self.setCursor(_EDGE_CURSORS.get(frozenset(edges), Qt.ArrowCursor))
        super().mouseMoveEvent(ev)


class CaptionButton(QPushButton):
    MIN, MAX, RESTORE, CLOSE = "min", "max", "restore", "close"

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(_BTN_WIDTH, HEADER_HEIGHT)
        self.setFlat(True)
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 0; }"
            f"QPushButton:hover {{ background: {'#e81123' if kind == self.CLOSE else BORDER}; }}"
        )

    def paintEvent(self, ev) -> None:
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(TEXT))
        pen.setWidthF(1.2)
        p.setPen(pen)
        cx, cy, s = self.width() / 2, self.height() / 2, 5
        if self.kind == self.MIN:
            p.drawLine(int(cx - s), int(cy), int(cx + s), int(cy))
        elif self.kind == self.MAX:
            p.drawRect(int(cx - s), int(cy - s), 2 * s, 2 * s)
        elif self.kind == self.RESTORE:
            p.drawRect(int(cx - s + 3), int(cy - s), 2 * s - 3, 2 * s - 3)
            p.fillRect(int(cx - s), int(cy - s + 3), 2 * s - 3, 2 * s - 3, QColor(BG))
            p.drawRect(int(cx - s), int(cy - s + 3), 2 * s - 3, 2 * s - 3)
        elif self.kind == self.CLOSE:
            p.drawLine(int(cx - s), int(cy - s), int(cx + s), int(cy + s))
            p.drawLine(int(cx - s), int(cy + s), int(cx + s), int(cy - s))
        p.end()


class MaximizeButton(CaptionButton):
    def __init__(self, window, parent=None):
        super().__init__(self.MAX, parent)
        self._window = window
        self.clicked.connect(self._toggle)

    def _toggle(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def paintEvent(self, ev) -> None:
        self.kind = self.RESTORE if self._window.isMaximized() else self.MAX
        super().paintEvent(ev)


class TitleBar(QWidget):
    def __init__(self, window, icon: QIcon, parent=None):
        super().__init__(parent)
        self._window = window
        self.setObjectName("titleBar")
        self.setFixedHeight(HEADER_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(2)

        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(16, 16))
        lay.addWidget(icon_label)
        lay.addSpacing(6)

        self.menu_bar = QMenuBar()
        self.menu_bar.setNativeMenuBar(False)
        self.menu_bar.setStyleSheet("QMenuBar { background: transparent; border: none; }")
        lay.addWidget(self.menu_bar)
        lay.addStretch(1)

        min_btn = CaptionButton(CaptionButton.MIN)
        min_btn.clicked.connect(window.showMinimized)
        max_btn = MaximizeButton(window)
        close_btn = CaptionButton(CaptionButton.CLOSE)
        close_btn.clicked.connect(window.close)
        for b in (min_btn, max_btn, close_btn):
            lay.addWidget(b)

    def _is_empty_area(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        return child is None or child is self

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self._is_empty_area(ev.position().toPoint()):
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev) -> None:
        if self._is_empty_area(ev.position().toPoint()):
            if self._window.isMaximized():
                self._window.showNormal()
            else:
                self._window.showMaximized()
            return
        super().mouseDoubleClickEvent(ev)
