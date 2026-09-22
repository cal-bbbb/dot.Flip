"""Batch conversion window."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.batch import Result, run_batch
from ..core.convert import ConvertOptions
from ..core.formats import READ_EXTENSIONS, WRITABLE, format_for_path, get_format
from .options_panel import OptionsPanel

COLS = ["File", "Type", "Size", "Status"]


class Worker(QThread):
    progress = Signal(int, int, object)
    finished_all = Signal(object)

    def __init__(self, files, opts):
        super().__init__()
        self.files, self.opts = files, opts
        self.cancel = threading.Event()

    def run(self):
        res = run_batch(self.files, self.opts, on_progress=lambda d, t, r: self.progress.emit(d, t, r), cancel=self.cancel)
        self.finished_all.emit(res)


def _asset_dir() -> Path:
    """Repo-root ``assets/`` in dev, or the copy PyInstaller bundles alongside the frozen app."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "assets" if base else Path(__file__).resolve().parents[3] / "assets"


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class MainWindow(QMainWindow):
    def __init__(self, files=()):
        super().__init__()
        self.setWindowTitle("dot.Flip")
        self.setWindowIcon(QIcon(str(_asset_dir() / "icon.png")))  # top-left of the title bar, and the taskbar
        self.resize(1000, 640)
        self.setAcceptDrops(True)
        self.settings = QSettings("dotflip", "dotflip")
        self.worker: Worker | None = None
        self.bg = QColor(255, 255, 255)
        self.rows: dict[Path, int] = {}

        header = self._build_header()

        splitter = QSplitter()
        splitter.addWidget(self._build_files())
        splitter.addWidget(self._build_settings())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setDefault(True)
        self.convert_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel)
        bottom = QHBoxLayout()
        bottom.addWidget(self.progress, 1)
        bottom.addWidget(self.cancel_btn)
        bottom.addWidget(self.convert_btn)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(header)
        lay.addWidget(splitter, 1)
        lay.addLayout(bottom)
        self.setCentralWidget(central)
        self.add_files(files)
        self.statusBar().showMessage("Drop images or folders here")

    # ---- construction -------------------------------------------------
    def _build_files(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        lay.addWidget(self.table, 1)
        return box

    def _build_settings(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)

        out = QGroupBox("Convert to")
        f = QFormLayout(out)
        self.target = QComboBox()
        for fmt in WRITABLE:
            self.target.addItem(fmt.label, fmt.name)
        self.target.setCurrentText(self.settings.value("target", "PNG"))
        self.target.currentIndexChanged.connect(self._target_changed)
        f.addRow("Format", self.target)
        self.options = OptionsPanel()
        f.addRow(self.options)
        lay.addWidget(out)

        rz = QGroupBox("Resize")
        f = QFormLayout(rz)
        self.resize_mode = QComboBox()
        self.resize_mode.addItems(["Original size", "Percent", "Fit within (keeps aspect)"])
        self.resize_mode.currentIndexChanged.connect(self._resize_changed)
        self.pct = QDoubleSpinBox()
        self.pct.setRange(1, 1000)
        self.pct.setValue(50)
        self.pct.setSuffix(" %")
        self.max_w, self.max_h = QSpinBox(), QSpinBox()
        for s in (self.max_w, self.max_h):
            s.setRange(0, 100000)
            s.setSpecialValueText("any")
            s.setSuffix(" px")
        self.max_w.setValue(1920)
        self.max_h.setValue(1080)
        f.addRow(self.resize_mode)
        f.addRow("Percent", self.pct)
        f.addRow("Max width", self.max_w)
        f.addRow("Max height", self.max_h)
        self.svg_w = QSpinBox()
        self.svg_w.setRange(0, 20000)
        self.svg_w.setSpecialValueText("intrinsic")
        self.svg_w.setSuffix(" px")
        f.addRow("SVG render width", self.svg_w)
        self._resize_changed()
        lay.addWidget(rz)

        misc = QGroupBox("Image")
        f = QFormLayout(misc)
        self.bg_btn = QPushButton()
        self._set_bg(self.bg)
        self.bg_btn.clicked.connect(self._pick_bg)
        f.addRow("Background for transparency", self.bg_btn)
        self.keep_meta = QCheckBox("Keep metadata (EXIF, color profile)")
        self.keep_meta.setChecked(True)
        f.addRow(self.keep_meta)
        lay.addWidget(misc)

        dest = QGroupBox("Output")
        f = QFormLayout(dest)
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Same folder as each source file")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.pick_out)
        row = QHBoxLayout()
        row.addWidget(self.out_dir, 1)
        row.addWidget(browse)
        f.addRow("Folder", row)
        self.template = QLineEdit("{name}")
        self.template.setToolTip("Use {name} for the original file name, e.g. {name}_converted")
        f.addRow("File name", self.template)
        self.collision = QComboBox()
        self.collision.addItem("Rename (add number)", "rename")
        self.collision.addItem("Overwrite", "overwrite")
        self.collision.addItem("Skip", "skip")
        f.addRow("If file exists", self.collision)
        self.delete_orig = QCheckBox("Delete original after successful conversion")
        f.addRow(self.delete_orig)
        lay.addWidget(dest)
        lay.addStretch(1)
        self._target_changed()
        return box

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for text, fn in (("Add files...", self.pick_files), ("Add folder...", self.pick_folder),
                         ("Remove selected", self.remove_selected), ("Clear", self.clear)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)

        settings_menu = QMenu(self)
        for text, fn in (("Install right-click menu", self.install_menu), ("Remove right-click menu", self.remove_menu)):
            a = QAction(text, self)
            a.triggered.connect(fn)
            settings_menu.addAction(a)
        settings_btn = QPushButton("Settings")
        settings_btn.setMenu(settings_menu)
        row.addWidget(settings_btn)
        return row

    # ---- settings helpers --------------------------------------------
    def _target_changed(self):
        fmt = get_format(self.target.currentData())
        self.options.set_format(fmt)
        self.settings.setValue("target", self.target.currentText())

    def _resize_changed(self):
        i = self.resize_mode.currentIndex()
        self.pct.setEnabled(i == 1)
        self.max_w.setEnabled(i == 2)
        self.max_h.setEnabled(i == 2)

    def _set_bg(self, c: QColor):
        self.bg = c
        self.bg_btn.setText(c.name().upper())
        self.bg_btn.setStyleSheet(f"background:{c.name()}; color:{'#000' if c.lightness() > 128 else '#fff'};")

    def _pick_bg(self):
        c = QColorDialog.getColor(self.bg, self)
        if c.isValid():
            self._set_bg(c)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    def build_options(self) -> ConvertOptions:
        mode = self.resize_mode.currentIndex()
        resize = None
        if mode == 1:
            resize = ("percent", self.pct.value())
        elif mode == 2:
            resize = ("fit", (self.max_w.value() or None, self.max_h.value() or None))
        return ConvertOptions(
            target=self.target.currentData(), format_options=self.options.values(), resize=resize,
            background=(self.bg.red(), self.bg.green(), self.bg.blue()), keep_metadata=self.keep_meta.isChecked(),
            svg_width=self.svg_w.value() or None, output_dir=Path(self.out_dir.text()) if self.out_dir.text() else None,
            name_template=self.template.text() or "{name}", collision=self.collision.currentData(),
            delete_original=self.delete_orig.isChecked(),
        )

    # ---- file list ----------------------------------------------------
    def add_files(self, paths):
        for p in map(Path, paths):
            children = [c for c in sorted(p.iterdir()) if c.is_file()] if p.is_dir() else [p]
            for c in children:
                fmt = format_for_path(c)
                if fmt is None or c in self.rows:
                    continue
                r = self.table.rowCount()
                self.table.insertRow(r)
                for col, text in enumerate((c.name, fmt.label, _human(c.stat().st_size), "Ready")):
                    item = QTableWidgetItem(text)
                    item.setData(Qt.UserRole, str(c))
                    item.setToolTip(str(c))
                    self.table.setItem(r, col, item)
                self.rows[c] = r
        self._reindex()
        self.statusBar().showMessage(f"{self.table.rowCount()} file(s)")

    def _reindex(self):
        self.rows = {Path(self.table.item(r, 0).data(Qt.UserRole)): r for r in range(self.table.rowCount())}

    def all_files(self) -> list[Path]:
        return list(self.rows)

    def pick_files(self):
        exts = " ".join(f"*{e}" for e in READ_EXTENSIONS)
        files, _ = QFileDialog.getOpenFileNames(self, "Add images", "", f"Images ({exts});;All files (*)")
        self.add_files(files)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder")
        if d:
            self.add_files([d])

    def remove_selected(self):
        for r in sorted({i.row() for i in self.table.selectedItems()}, reverse=True):
            self.table.removeRow(r)
        self._reindex()

    def clear(self):
        self.table.setRowCount(0)
        self._reindex()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # ---- running ------------------------------------------------------
    def _set_status(self, src: Path, text: str, color: str | None = None):
        r = self.rows.get(src)
        if r is None:
            return
        item = self.table.item(r, 3)
        item.setText(text)
        item.setForeground(QColor(color) if color else QApplication.palette().text())

    def start(self):
        files = self.all_files()
        if not files:
            QMessageBox.information(self, "dot.Flip", "Add some images first.")
            return
        if self.delete_orig.isChecked() and QMessageBox.question(
            self, "Delete originals?", f"Original files will be deleted after conversion ({len(files)} file(s)). Continue?"
        ) != QMessageBox.Yes:
            return
        for f in files:
            self._set_status(f, "Queued")
        self.worker = Worker(files, self.build_options())
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_all.connect(self._on_done)
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.convert_btn.setEnabled(False)
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, done: int, total: int, r: Result):
        self.progress.setValue(done)
        if r.error:
            self._set_status(r.source, "Failed: " + r.error, "#c0392b")
        elif r.cancelled:
            self._set_status(r.source, "Cancelled", "#888888")
        elif r.skipped:
            self._set_status(r.source, "Skipped (exists)", "#888888")
        else:
            self._set_status(r.source, f"Done -> {r.output.name}", "#27ae60")

    def _on_done(self, results):
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self.convert_btn.setEnabled(True)
        ok = sum(1 for r in results if r.ok and not r.skipped)
        bad = sum(1 for r in results if r.error)
        self.statusBar().showMessage(f"Finished: {ok} converted, {bad} failed")
        outs = [r.output for r in results if r.output]
        if outs and bad == 0 and QMessageBox.question(self, "Done", f"Converted {ok} file(s). Open output folder?") == QMessageBox.Yes:
            os.startfile(outs[0].parent)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.worker.wait(5000)
        e.accept()

    # ---- Explorer integration ----------------------------------------
    def install_menu(self):
        from ..shell import register

        n = register.install()
        if n == 0:
            QMessageBox.information(self, "dot.Flip", "The Windows 11 right-click menu is already active, so nothing more was added.")
            return
        QMessageBox.information(self, "dot.Flip", f"Right-click menu installed for {n} file types.")

    def remove_menu(self):
        from ..shell import register

        n = register.uninstall()
        QMessageBox.information(self, "dot.Flip", f"Right-click menu removed from {n} file types.")
