"""Left-hand file list: a detail table or a media (icon) grid, switched by header tabs."""
from __future__ import annotations

from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QItemSelection, QItemSelectionModel, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHeaderView, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.formats import format_for_path
from .crop_panel import load_preview
from .widgets import HEADER_HEIGHT, TabHeader

COLS = ["File", "Status"]
_THUMB = 72


def _thumbnail_icon(path: Path) -> QIcon:
    img, _ = load_preview(path, max_side=_THUMB)
    if img is None:
        return QIcon()
    return QIcon(QPixmap.fromImage(ImageQt(img)))


class FileBrowser(QWidget):
    """Owns the file set, a table view and a grid view of it, kept in sync, plus the tab header."""

    selectionChanged = Signal()
    filesChanged = Signal()  # files added/removed/cleared

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: dict[Path, int] = {}  # path -> order index, for callers that need a stable position
        self._order: list[Path] = []
        self._syncing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = TabHeader(["List", "Media"])
        self.header.currentChanged.connect(self._set_view_mode)
        lay.addWidget(self.header)

        self.table = self._build_table()
        self.grid = self._build_grid()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.grid)
        lay.addWidget(self.stack, 1)

        bottom = QWidget()
        bottom_lay = QVBoxLayout(bottom)
        bottom_lay.setContentsMargins(8, 8, 8, 8)
        self.browse_btn = QPushButton("Browse...")
        bottom_lay.addWidget(self.browse_btn)
        lay.addWidget(bottom)

        menu = QMenu(self)
        self.add_files_action = menu.addAction("Add files...")
        self.add_folder_action = menu.addAction("Add folder...")
        menu.addSeparator()
        self.remove_action = menu.addAction("Remove selected")
        self.clear_action = menu.addAction("Clear")
        self.header.hamburger.set_menu(menu)

    # ---- construction ---------------------------------------------------
    def _build_table(self) -> QTableWidget:
        t = QTableWidget(0, len(COLS))
        t.setHorizontalHeaderLabels(COLS)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setShowGrid(False)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setFixedHeight(HEADER_HEIGHT)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.itemSelectionChanged.connect(self._on_table_selection)
        t.itemChanged.connect(self._on_item_changed)
        return t

    def _build_grid(self) -> QListWidget:
        g = QListWidget()
        g.setViewMode(QListWidget.IconMode)
        g.setIconSize(QSize(_THUMB, _THUMB))
        g.setResizeMode(QListWidget.Adjust)
        g.setMovement(QListWidget.Static)
        g.setSpacing(10)
        g.setWordWrap(True)
        g.setSelectionMode(QAbstractItemView.ExtendedSelection)
        g.itemSelectionChanged.connect(self._on_grid_selection)
        return g

    # ---- view mode --------------------------------------------------------
    def _set_view_mode(self, id_: int) -> None:
        selected = self.selected_files()
        if id_ == 1:
            self._populate_grid()
        self.stack.setCurrentIndex(id_)
        self._select_paths(selected)

    # ---- file list ----------------------------------------------------
    def add_files(self, paths) -> None:
        added = False
        for p in map(Path, paths):
            children = [c for c in sorted(p.iterdir()) if c.is_file()] if p.is_dir() else [p]
            for c in children:
                fmt = format_for_path(c)
                if fmt is None or c in self.rows:
                    continue
                self._order.append(c)
                self._add_table_row(c)
                added = True
        if added:
            self._reindex()
            if self.stack.currentIndex() == 1:
                self._populate_grid()
            self.filesChanged.emit()

    def _add_table_row(self, path: Path) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.blockSignals(True)
        name_item = QTableWidgetItem(path.name)
        name_item.setData(Qt.UserRole, str(path))
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setCheckState(Qt.Unchecked)
        self.table.setItem(r, 0, name_item)
        status_item = QTableWidgetItem("Ready")
        status_item.setData(Qt.UserRole, str(path))
        self.table.setItem(r, 1, status_item)
        self.table.blockSignals(False)

    def _populate_grid(self) -> None:
        self.grid.clear()
        for path in self._order:
            item = QListWidgetItem(_thumbnail_icon(path), path.name)
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            self.grid.addItem(item)

    def _reindex(self) -> None:
        self.rows = {p: i for i, p in enumerate(self._order)}

    def remove_selected(self) -> None:
        selected = set(self.selected_files())
        if not selected:
            return
        self._order = [p for p in self._order if p not in selected]
        for r in sorted(
            (r for r in range(self.table.rowCount()) if Path(self.table.item(r, 0).data(Qt.UserRole)) in selected),
            reverse=True,
        ):
            self.table.removeRow(r)
        if self.stack.currentIndex() == 1:
            self._populate_grid()
        self._reindex()
        self.filesChanged.emit()

    def clear(self) -> None:
        self._order = []
        self.table.setRowCount(0)
        self.grid.clear()
        self._reindex()
        self.filesChanged.emit()

    def all_files(self) -> list[Path]:
        return list(self._order)

    def set_status(self, path: Path, text: str, color: str | None = None) -> None:
        r = self.rows.get(path)
        if r is None:
            return
        item = self.table.item(r, 1)
        item.setText(text)
        item.setForeground(QColor(color) if color else QApplication.palette().text())

    # ---- selection ------------------------------------------------------
    def selected_files(self) -> list[Path]:
        if self.stack.currentIndex() == 1:
            return [Path(i.data(Qt.UserRole)) for i in self.grid.selectedItems()]
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [Path(self.table.item(r, 0).data(Qt.UserRole)) for r in rows]

    def _select_paths(self, paths) -> None:
        wanted = {str(p) for p in paths}
        self._syncing = True
        try:
            if self.stack.currentIndex() == 1:
                for i in range(self.grid.count()):
                    item = self.grid.item(i)
                    item.setSelected(item.data(Qt.UserRole) in wanted)
            else:
                model = self.table.model()
                selection = QItemSelection()
                for r in range(self.table.rowCount()):
                    if self.table.item(r, 0).data(Qt.UserRole) in wanted:
                        selection.select(model.index(r, 0), model.index(r, self.table.columnCount() - 1))
                self.table.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        finally:
            self._syncing = False

    def _on_table_selection(self) -> None:
        selected_rows = {i.row() for i in self.table.selectedItems()}
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked if r in selected_rows else Qt.Unchecked)
        self.table.blockSignals(False)
        if not self._syncing:
            self.selectionChanged.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        # The checkbox is a read-only mirror of row selection; snap back if toggled directly.
        if item.column() != 0:
            return
        selected_rows = {i.row() for i in self.table.selectedItems()}
        wanted = Qt.Checked if item.row() in selected_rows else Qt.Unchecked
        if item.checkState() != wanted:
            item.setCheckState(wanted)

    def _on_grid_selection(self) -> None:
        if not self._syncing:
            self.selectionChanged.emit()
