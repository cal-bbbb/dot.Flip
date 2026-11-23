"""Flat monochrome dark theme with a single blue accent, matching the user-supplied mockup.

No boxed/bordered group panels: sections are separated by thin divider lines and header
labels. Fields share the surrounding panel background and are defined only by a subtle border.
"""
from __future__ import annotations

BG = "#4d4d4d"          # window/panel background (flat, used almost everywhere)
BG_HEADER = "#404040"   # panel header / tab-strip strip
BG_WELL = "#262627"     # recessed content well: the file list and media grid
BORDER = "#636363"      # subtle field/divider borders
DARK_LINE = "#3a3a3a"   # row separators, section dividers (slightly darker than BG)
TEXT = "#dcdcdc"        # primary text
TEXT_MUTED = "#8f8f8f"  # secondary text, inactive tab, section labels
TEXT_DIM = "#6e6e6e"    # placeholder / disabled text
ROW_SELECTED = "#7a7a7a"  # selected list row background
FILL_LIGHT = "#e6e6e6"    # checked checkbox, selected origin cell, crop handles (near-white)
FILL_MID = "#c2c2c2"      # selected ratio/tab-style toggle button
ACCENT = "#0088ff"        # Convert button, color swatches, crop box
ACCENT_HOVER = "#2a9bff"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 12px;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QToolTip {{
    background: {BG_HEADER};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 3px 6px;
}}

QMenuBar {{
    background: {BG};
    color: {TEXT};
    border-bottom: 1px solid {DARK_LINE};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}}
QMenuBar::item:selected {{
    background: {BG_HEADER};
}}
QMenu {{
    background: {BG_HEADER};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QMenu::item {{
    padding: 5px 20px;
}}
QMenu::item:selected {{
    background: {ROW_SELECTED};
}}

QLabel {{
    background: transparent;
    color: {TEXT};
}}
QLabel[role="section"] {{
    color: {TEXT_MUTED};
    font-weight: 600;
}}
QLabel[role="placeholder"] {{
    color: {TEXT_MUTED};
}}
QFrame[role="divider"] {{
    background: {DARK_LINE};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QPushButton {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 4px 10px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: {BG_HEADER};
}}
QPushButton:pressed {{
    background: {ROW_SELECTED};
}}
QPushButton:checkable:checked {{
    background: {FILL_MID};
    border-color: {FILL_MID};
    color: #1b1b1b;
    font-weight: 600;
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border-color: {DARK_LINE};
}}
QPushButton#convertButton {{
    background: {ACCENT};
    border: none;
    border-radius: 4px;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
    padding: 10px;
}}
QPushButton#convertButton:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#convertButton:disabled {{
    background: {BG_HEADER};
    color: {TEXT_DIM};
}}
QPushButton[role="tab"] {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 6px 10px;
    color: {TEXT_MUTED};
    font-weight: 600;
}}
QPushButton[role="tab"]:checked {{
    background: transparent;
    color: {TEXT};
}}
QPushButton[role="tab"]:hover {{
    color: {TEXT};
}}
QPushButton[role="plain"] {{
    border: none;
    background: transparent;
}}
QPushButton[role="plain"]:hover {{
    background: {BG_HEADER};
}}
QPushButton[role="origin-cell"] {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 2px;
    padding: 0;
}}
QPushButton[role="origin-cell"]:checked {{
    background: {FILL_LIGHT};
    border-color: {FILL_LIGHT};
}}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 2px 6px;
    selection-background-color: {ROW_SELECTED};
}}
QLineEdit:read-only {{
    color: {TEXT_MUTED};
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: {TEXT_DIM};
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_MUTED};
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {BG_HEADER};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ROW_SELECTED};
    selection-color: {TEXT};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 14px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid {TEXT_MUTED};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {TEXT_MUTED};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {BG_HEADER};
}}

QCheckBox {{
    spacing: 6px;
    color: {TEXT};
    background: transparent;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {BORDER};
    border-radius: 2px;
    background: transparent;
}}
QCheckBox::indicator:hover {{
    border-color: {TEXT};
}}
QCheckBox::indicator:checked {{
    background: {FILL_LIGHT};
    border-color: {FILL_LIGHT};
}}
QCheckBox::indicator:indeterminate {{
    background: {TEXT_MUTED};
    border-color: {TEXT_MUTED};
}}

QSlider::groove:horizontal {{
    height: 2px;
    background: {BORDER};
    border-radius: 1px;
}}
QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    background: {FILL_LIGHT};
    border: none;
    border-radius: 6px;
}}
QSlider::sub-page:horizontal {{
    background: {TEXT_MUTED};
    border-radius: 1px;
}}

QTableWidget, QListView {{
    background: {BG_WELL};
    alternate-background-color: {BG_WELL};
    color: {TEXT};
    border: none;
    outline: none;
    gridline-color: transparent;
}}
QTableWidget::item {{
    border-bottom: 1px solid {DARK_LINE};
    padding: 4px 2px;
}}
QTableWidget::item:selected, QListView::item:selected {{
    background: {ROW_SELECTED};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {BG_WELL};
    color: {TEXT_MUTED};
    padding: 5px 4px;
    border: none;
    border-right: 1px solid {DARK_LINE};
    border-bottom: 1px solid {DARK_LINE};
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableCornerButton::section {{
    background: {BG_WELL};
    border: none;
}}

QProgressBar {{
    background: {BG_HEADER};
    border: 1px solid {BORDER};
    border-radius: 3px;
    text-align: center;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: {BG};
    border: none;
}}
QScrollBar::handle {{
    background: {BORDER};
    border-radius: 4px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}

QStatusBar {{
    background: {BG};
    color: {TEXT_MUTED};
    border-top: 1px solid {DARK_LINE};
}}

QSplitter::handle {{
    background: {DARK_LINE};
}}

QWidget#panelHeader, QWidget#tabHeader {{
    background: {BG_HEADER};
    border-bottom: 1px solid {DARK_LINE};
}}
QWidget#titleBar, QWidget#resizableRoot {{
    background: {BG};
}}
QWidget#zoomBar {{
    background: rgba(28, 28, 30, 210);
    border: 1px solid {BORDER};
    border-radius: 5px;
}}
QWidget#zoomBar QLabel {{
    color: {TEXT};
}}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
