"""Small reusable chrome: the hamburger icon, flat section labels/dividers, and panel headers.

The hamburger is drawn with QPainter rather than a unicode glyph — "☰" rendered as a blank
box in this environment's font, so a hand-drawn icon is the only reliable option.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from .theme import DARK_LINE, TEXT_MUTED

HEADER_HEIGHT = 32  # every grey header strip (tabs, Preview, Properties, Output, File Info) shares this


class HamburgerButton(QPushButton):
    """A small ≡ icon button that, if given a menu, shows it on click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "plain")
        self.setFixedSize(24, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._menu: QMenu | None = None

    def set_menu(self, menu: QMenu) -> None:
        self._menu = menu
        self.clicked.connect(lambda: menu.exec(self.mapToGlobal(self.rect().bottomRight())))

    def sizeHint(self) -> QSize:
        return QSize(24, 22)

    def paintEvent(self, ev) -> None:
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(TEXT_MUTED))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        half = 6
        for dy in (-5, 0, 5):
            p.drawLine(int(cx - half), int(cy + dy), int(cx + half), int(cy + dy))
        p.end()


def divider() -> QFrame:
    f = QFrame()
    f.setProperty("role", "divider")
    f.setFrameShape(QFrame.HLine)
    return f


def section_label(text: str) -> QLabel:
    l = QLabel(text)
    l.setProperty("role", "section")
    return l


def panel_header(title: str, menu: QMenu | None = None) -> QWidget:
    """A header strip: bold-ish title on the left, optional hamburger menu on the right."""
    box = QWidget()
    box.setObjectName("panelHeader")
    box.setFixedHeight(HEADER_HEIGHT)
    lay = QHBoxLayout(box)
    lay.setContentsMargins(10, 0, 4, 0)
    label = QLabel(title)
    label.setStyleSheet("font-weight:600; font-size:13px;")
    lay.addWidget(label)
    lay.addStretch(1)
    if menu is not None:
        ham = HamburgerButton()
        ham.set_menu(menu)
        lay.addWidget(ham)
    return box


class TabHeader(QWidget):
    """Header strip with text tabs (e.g. "List" / "Media") on the left and a hamburger on the right."""

    currentChanged = Signal(int)

    def __init__(self, tabs: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("tabHeader")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, name in enumerate(tabs):
            btn = QPushButton(name)
            btn.setProperty("role", "tab")
            btn.setCheckable(True)
            self._group.addButton(btn, i)
            lay.addWidget(btn)
            if i < len(tabs) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet(f"color:{DARK_LINE};")
                sep.setFixedWidth(1)
                lay.addWidget(sep)
        self._group.button(0).setChecked(True)
        lay.addStretch(1)
        self.hamburger = HamburgerButton()
        lay.addWidget(self.hamburger)
        self._group.idClicked.connect(self.currentChanged)
