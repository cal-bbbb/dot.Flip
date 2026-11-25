"""Batch conversion window: file list + info (left), preview (center), properties (right)."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..core.batch import Result, run_batch
from ..core.convert import ConvertOptions
from ..core.formats import WRITABLE, get_format
from .crop_panel import CropCanvas, CropControls, load_preview
from .file_browser import FileBrowser
from .file_info import FileInfoPanel
from .mixed import spin_set_mixed, spin_set_value
from .options_panel import OptionsPanel
from .theme import TEXT_MUTED
from .titlebar import ResizableRoot, TitleBar
from .widgets import divider, panel_header, section_label


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
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "assets" if base else Path(__file__).resolve().parents[3] / "assets"


class MainWindow(QMainWindow):
    def __init__(self, files=()):
        super().__init__()
        self.setWindowTitle("dot.Flip")
        self.setWindowIcon(QIcon(str(_asset_dir() / "DotFlip.ico")))
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.resize(1600, 820)
        self.setAcceptDrops(True)
        self.settings = QSettings("dotflip", "dotflip")
        self.worker: Worker | None = None
        self.bg = QColor(255, 255, 255)
        self.file_options: dict[Path, ConvertOptions] = {}
        self._syncing = False

        self.preview = CropCanvas()
        self.preview.changed.connect(self._on_preview_changed)

        self.files = FileBrowser()
        self.files.browse_btn.clicked.connect(self.pick_files)
        self.files.add_files_action.triggered.connect(self.pick_files)
        self.files.add_folder_action.triggered.connect(self.pick_folder)
        self.files.remove_action.triggered.connect(self.files.remove_selected)
        self.files.clear_action.triggered.connect(self.files.clear)
        self.files.filesChanged.connect(self._on_files_changed)
        self.files.selectionChanged.connect(self._sync_properties)

        root = ResizableRoot(self)
        self.title_bar = TitleBar(self, self.windowIcon())
        root.content_layout().addWidget(self.title_bar)
        self._build_menu_bar()

        splitter = QSplitter()
        splitter.setHandleWidth(2)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_preview())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([340, 800, 400])
        root.content_layout().addWidget(splitter, 1)

        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color:{TEXT_MUTED}; padding:3px 8px;")
        root.content_layout().addWidget(self.status_label)

        self.setCentralWidget(root)
        self.files.add_files(files)
        self._set_status("Drop images or folders here")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    # ---- top-level construction -----------------------------------------
    def _build_menu_bar(self) -> None:
        bar = self.title_bar.menu_bar
        bar.addMenu("File").addAction("Exit", self.close)

        edit_menu = bar.addMenu("Edit")
        edit_menu.addAction(self.files.remove_action)
        edit_menu.addAction(self.files.clear_action)

        add_menu = bar.addMenu("Add")
        add_menu.addAction(self.files.add_files_action)
        add_menu.addAction(self.files.add_folder_action)

        view_menu = bar.addMenu("View")
        view_menu.addAction("List", lambda: self.files.header._group.button(0).click())
        view_menu.addAction("Media", lambda: self.files.header._group.button(1).click())

        settings_menu = bar.addMenu("Settings")
        settings_menu.addAction("Install right-click menu", self.install_menu)
        settings_menu.addAction("Remove right-click menu", self.remove_menu)

    def _build_left(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.files, 2)
        self.file_info = FileInfoPanel()
        lay.addWidget(self.file_info, 1)
        return box

    def _build_preview(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(panel_header("Preview"))
        lay.addWidget(self.preview, 1)
        return box

    def _build_right(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_properties_panel(), 1)
        lay.addWidget(self._build_output_panel())
        return box

    # ---- properties panel -------------------------------------------------
    def _build_properties_panel(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(panel_header("Properties", QMenu()))

        self.properties_stack = QStackedWidget()
        placeholder = QLabel("Select a file to edit its settings.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px;")
        self.properties_stack.addWidget(placeholder)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self._build_properties_body())
        self.properties_stack.addWidget(scroll)
        lay.addWidget(self.properties_stack, 1)
        return box

    def _build_properties_body(self) -> QWidget:
        body = QWidget()
        f = QFormLayout(body)
        f.setContentsMargins(12, 10, 12, 10)
        f.setVerticalSpacing(7)

        f.addRow(section_label("Convert to"))
        self.target = QComboBox()
        for fmt in WRITABLE:
            self.target.addItem(fmt.label, fmt.name)
        self.target.currentIndexChanged.connect(self._on_target_changed)
        f.addRow("Format:", self.target)
        self.options = OptionsPanel()
        self.options.changed.connect(self._on_format_option_changed)
        f.addRow(self.options)

        f.addRow(divider())
        f.addRow(section_label("Resize"))
        self.resize_mode = QComboBox()
        self.resize_mode.addItems(["Original size", "Percent", "Fit within (keeps aspect)", "Crop to size"])
        self.resize_mode.currentIndexChanged.connect(self._on_resize_mode_changed)
        f.addRow(self.resize_mode)
        self.pct = QDoubleSpinBox()
        self.pct.setRange(1, 1000)
        self.pct.setSuffix(" %")
        self.pct.valueChanged.connect(self._on_pct_changed)
        self.max_w, self.max_h = QSpinBox(), QSpinBox()
        for s, handler in ((self.max_w, self._on_max_w_changed), (self.max_h, self._on_max_h_changed)):
            s.setRange(0, 100000)
            s.setSpecialValueText("any")
            s.setSuffix(" px")
            s.valueChanged.connect(handler)
        self.crop_controls = CropControls(self.preview)
        self._resize_form = f
        self._pct_row = f.rowCount()
        f.addRow("Percent:", self.pct)
        self._max_w_row = f.rowCount()
        f.addRow("Max width:", self.max_w)
        self._max_h_row = f.rowCount()
        f.addRow("Max height:", self.max_h)
        self._crop_row = f.rowCount()
        f.addRow(self.crop_controls)
        self.svg_w = QSpinBox()
        self.svg_w.setRange(0, 20000)
        self.svg_w.setSpecialValueText("intrinsic")
        self.svg_w.setSuffix(" px")
        self.svg_w.valueChanged.connect(self._on_svg_w_changed)
        f.addRow("SVG Render Width:", self.svg_w)

        f.addRow(divider())
        f.addRow(section_label("Image"))
        bg_row = QHBoxLayout()
        self.bg_swatch = QPushButton()
        self.bg_swatch.setFixedSize(20, 20)
        self.bg_swatch.clicked.connect(self._pick_bg)
        self.bg_hex = QLineEdit()
        self.bg_hex.editingFinished.connect(self._on_bg_hex_edited)
        bg_row.addWidget(self.bg_swatch)
        bg_row.addWidget(self.bg_hex, 1)
        f.addRow("Background Fill:", bg_row)
        self.keep_meta = QCheckBox()
        self.keep_meta.stateChanged.connect(self._on_keep_meta_changed)
        f.addRow("Keep Metadata:", self.keep_meta)
        self._set_bg(self.bg)
        return body

    # ---- output panel -----------------------------------------------------
    def _build_output_panel(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(panel_header("Output", QMenu()))

        body = QWidget()
        f = QFormLayout(body)
        f.setContentsMargins(12, 10, 12, 10)
        f.addRow(section_label("Destination"))
        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Same folder as source")
        self.out_dir.textChanged.connect(self._on_out_dir_changed)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.pick_out)
        row = QHBoxLayout()
        row.addWidget(self.out_dir, 1)
        row.addWidget(browse)
        f.addRow("Folder:", row)
        self.template = QLineEdit()
        self.template.setPlaceholderText("{name}")
        self.template.setToolTip("Use {name} for the original file name, e.g. {name}_converted")
        self.template.textChanged.connect(self._on_template_changed)
        f.addRow("File Name:", self.template)
        self.collision = QComboBox()
        self.collision.addItem("Rename (add number)", "rename")
        self.collision.addItem("Overwrite", "overwrite")
        self.collision.addItem("Skip", "skip")
        self.collision.currentIndexChanged.connect(self._on_collision_changed)
        f.addRow("If Conflict:", self.collision)
        self.delete_orig = QCheckBox()
        self.delete_orig.stateChanged.connect(self._on_delete_orig_changed)
        f.addRow("Delete original:", self.delete_orig)
        lay.addWidget(body)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 12)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setObjectName("convertButton")
        self.convert_btn.setDefault(True)
        self.convert_btn.clicked.connect(self.start)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.convert_btn, 1)
        lay.addLayout(btn_row)
        return box

    # ---- per-file options -----------------------------------------------
    def _default_options(self) -> ConvertOptions:
        try:
            target = get_format(self.settings.value("target", "png")).name
        except ValueError:
            target = "png"
        return ConvertOptions(target=target)

    def _effective_selection(self) -> list[Path]:
        selected = self.files.selected_files()
        return selected if selected else self.files.all_files()

    def _on_files_changed(self) -> None:
        current = set(self.files.all_files())
        for f in current:
            if f not in self.file_options:
                self.file_options[f] = self._default_options()
        for f in list(self.file_options):
            if f not in current:
                del self.file_options[f]
        self._set_status(f"{len(current)} file(s)")
        self._sync_properties()

    def _shared(self, opts_list, getter):
        """Returns (value, is_mixed): the common value across opts_list, or (first value, True)."""
        values = [getter(o) for o in opts_list]
        if all(v == values[0] for v in values):
            return values[0], False
        return values[0], True

    def _commit(self, attr: str, value) -> None:
        if self._syncing:
            return
        for f in self._effective_selection():
            setattr(self.file_options[f], attr, value)

    # ---- sync: file_options -> widgets -----------------------------------
    def _sync_properties(self) -> None:
        if not self.files.all_files():
            self.properties_stack.setCurrentIndex(0)
            self.preview.set_interactive(False)
            self.preview.set_image(None, (0, 0))
            self.file_info.set_path(None)
            return
        self.properties_stack.setCurrentIndex(1)
        selection = self._effective_selection()
        opts_list = [self.file_options[f] for f in selection]
        self._syncing = True
        try:
            self._sync_target(opts_list)
            self._sync_resize(opts_list)
            self._sync_image(opts_list)
            self._sync_output(opts_list)
        finally:
            self._syncing = False
        self._sync_preview_source(selection)

    def _sync_target(self, opts_list) -> None:
        target, mixed = self._shared(opts_list, lambda o: o.target)
        self.target.blockSignals(True)
        self.target.setCurrentIndex(-1 if mixed else self.target.findData(target))
        self.target.blockSignals(False)
        if mixed:
            self.options.set_format_message("Multiple formats selected.")
            return
        fmt = get_format(target)
        values, mixed_keys = {}, set()
        for opt in fmt.options:
            vals = [o.format_options.get(opt.key, opt.default) for o in opts_list]
            if all(v == vals[0] for v in vals):
                values[opt.key] = vals[0]
            else:
                mixed_keys.add(opt.key)
        self.options.set_format(fmt, values, frozenset(mixed_keys))

    def _sync_resize(self, opts_list) -> None:
        kinds = {(o.resize[0] if o.resize else None) for o in opts_list}
        mode_map = {None: 0, "percent": 1, "fit": 2, "crop": 3}
        mode = mode_map[next(iter(kinds))] if len(kinds) == 1 else -1
        self.resize_mode.blockSignals(True)
        self.resize_mode.setCurrentIndex(mode)
        self.resize_mode.blockSignals(False)
        self._show_resize_rows(mode)

        if mode == 1:
            pct, mixed = self._shared(opts_list, lambda o: o.resize[1])
            spin_set_mixed(self.pct, 1) if mixed else spin_set_value(self.pct, pct)
        elif mode == 2:
            w, wmix = self._shared(opts_list, lambda o: o.resize[1][0] or 0)
            h, hmix = self._shared(opts_list, lambda o: o.resize[1][1] or 0)
            self.max_w.setValue(w)
            self.max_h.setValue(h)
        elif mode == 3:
            box, mixed = self._shared(opts_list, lambda o: o.resize[1])
            self.preview.set_box(box)

        # svg_w already uses its specialValueText for "intrinsic" at 0, so it falls back to showing
        # the first file's value on a mixed selection rather than a second, conflicting sentinel.
        svg_w, _svg_mixed = self._shared(opts_list, lambda o: o.svg_width or 0)
        self.svg_w.setValue(svg_w)
        self.preview.set_interactive(mode == 3)

    def _show_resize_rows(self, mode: int) -> None:
        self._resize_form.setRowVisible(self._pct_row, mode == 1)
        self._resize_form.setRowVisible(self._max_w_row, mode == 2)
        self._resize_form.setRowVisible(self._max_h_row, mode == 2)
        self._resize_form.setRowVisible(self._crop_row, mode == 3)

    def _sync_image(self, opts_list) -> None:
        bg, bg_mixed = self._shared(opts_list, lambda o: o.background)
        self.bg_hex.blockSignals(True)
        if bg_mixed:
            self.bg_hex.setText("")
            self.bg_hex.setPlaceholderText("(multi)")
            self.bg_swatch.setStyleSheet("background:transparent; border:1px solid #888;")
        else:
            self._set_bg(QColor(*bg))
        self.bg_hex.blockSignals(False)
        keep, keep_mixed = self._shared(opts_list, lambda o: o.keep_metadata)
        self.keep_meta.blockSignals(True)
        if keep_mixed:
            self.keep_meta.setTristate(True)
            self.keep_meta.setCheckState(Qt.PartiallyChecked)
        else:
            self.keep_meta.setTristate(False)
            self.keep_meta.setChecked(keep)
        self.keep_meta.blockSignals(False)

    def _sync_output(self, opts_list) -> None:
        out_dir, dir_mixed = self._shared(opts_list, lambda o: str(o.output_dir) if o.output_dir else "")
        self.out_dir.blockSignals(True)
        self.out_dir.setText("" if dir_mixed else out_dir)
        self.out_dir.setPlaceholderText("(multiple folders)" if dir_mixed else "Same folder as source")
        self.out_dir.blockSignals(False)

        name, name_mixed = self._shared(opts_list, lambda o: o.name_template)
        self.template.blockSignals(True)
        self.template.setText("" if name_mixed else name)
        self.template.setPlaceholderText("(multi)" if name_mixed else "{name}")
        self.template.blockSignals(False)

        coll, coll_mixed = self._shared(opts_list, lambda o: o.collision)
        self.collision.blockSignals(True)
        self.collision.setCurrentIndex(-1 if coll_mixed else self.collision.findData(coll))
        self.collision.blockSignals(False)

        delete, delete_mixed = self._shared(opts_list, lambda o: o.delete_original)
        self.delete_orig.blockSignals(True)
        if delete_mixed:
            self.delete_orig.setTristate(True)
            self.delete_orig.setCheckState(Qt.PartiallyChecked)
        else:
            self.delete_orig.setTristate(False)
            self.delete_orig.setChecked(delete)
        self.delete_orig.blockSignals(False)

    def _sync_preview_source(self, selection) -> None:
        path = selection[0] if selection else None
        img, native = load_preview(path)
        self.preview.set_image(img, native)
        self.file_info.set_path(path)

    # ---- widgets -> file_options (live, applies to the effective selection) ----
    def _on_target_changed(self) -> None:
        data = self.target.currentData()
        if data is None or self._syncing:
            return
        self._commit("target", data)
        self.settings.setValue("target", data)
        self._sync_target([self.file_options[f] for f in self._effective_selection()])

    def _on_format_option_changed(self, key, value) -> None:
        if self._syncing:
            return
        for f in self._effective_selection():
            self.file_options[f].format_options[key] = value

    def _on_resize_mode_changed(self) -> None:
        if self._syncing:
            return
        mode = self.resize_mode.currentIndex()
        self._show_resize_rows(mode)
        self.preview.set_interactive(mode == 3)
        if mode == 0:
            self._commit("resize", None)
        elif mode == 1:
            self._commit("resize", ("percent", 50.0))
            spin_set_value(self.pct, 50.0)
        elif mode == 2:
            self._commit("resize", ("fit", (1920, 1080)))
            self.max_w.setValue(1920)
            self.max_h.setValue(1080)
        elif mode == 3:
            box = self.preview.box()
            self._commit("resize", ("crop", box))

    def _on_pct_changed(self, value) -> None:
        if self.pct.specialValueText():
            self.pct.setSpecialValueText("")
        self._commit("resize", ("percent", value))

    def _on_max_w_changed(self, value) -> None:
        self._commit("resize", ("fit", (value or None, self.max_h.value() or None)))

    def _on_max_h_changed(self, value) -> None:
        self._commit("resize", ("fit", (self.max_w.value() or None, value or None)))

    def _on_svg_w_changed(self, value) -> None:
        if self.svg_w.specialValueText():
            self.svg_w.setSpecialValueText("")
        self._commit("svg_width", value or None)

    def _on_preview_changed(self) -> None:
        if self._syncing or not self.preview.interactive:
            return
        self._commit("resize", ("crop", self.preview.box()))

    def _on_keep_meta_changed(self, state) -> None:
        if Qt.CheckState(state) == Qt.PartiallyChecked:
            return
        self.keep_meta.setTristate(False)
        self._commit("keep_metadata", self.keep_meta.isChecked())

    def _on_out_dir_changed(self, text) -> None:
        self._commit("output_dir", Path(text) if text else None)

    def _on_template_changed(self, text) -> None:
        self._commit("name_template", text or "{name}")

    def _on_collision_changed(self) -> None:
        data = self.collision.currentData()
        if data is not None:
            self._commit("collision", data)

    def _on_delete_orig_changed(self, state) -> None:
        if Qt.CheckState(state) == Qt.PartiallyChecked:
            return
        self.delete_orig.setTristate(False)
        self._commit("delete_original", self.delete_orig.isChecked())

    # ---- misc helpers --------------------------------------------------
    def _set_bg(self, c: QColor):
        self.bg = c
        self.bg_swatch.setStyleSheet(f"background:{c.name()}; border:1px solid #888; border-radius:2px;")
        self.bg_hex.blockSignals(True)
        self.bg_hex.setText(c.name().upper())
        self.bg_hex.blockSignals(False)

    def _pick_bg(self):
        c = QColorDialog.getColor(self.bg, self)
        if c.isValid():
            self._set_bg(c)
            self._commit("background", (c.red(), c.green(), c.blue()))

    def _on_bg_hex_edited(self):
        c = QColor(self.bg_hex.text())
        if c.isValid():
            self._set_bg(c)
            self._commit("background", (c.red(), c.green(), c.blue()))
        else:
            self._set_bg(self.bg)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    # ---- file list ----------------------------------------------------
    def pick_files(self):
        from ..core.formats import READ_EXTENSIONS

        exts = " ".join(f"*{e}" for e in READ_EXTENSIONS)
        paths, _ = QFileDialog.getOpenFileNames(self, "Add images", "", f"Images ({exts});;All files (*)")
        self.files.add_files(paths)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add folder")
        if d:
            self.files.add_files([d])

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.files.add_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # ---- running ------------------------------------------------------
    def start(self):
        files = self.files.all_files()
        if not files:
            QMessageBox.information(self, "dot.Flip", "Add some images first.")
            return
        if any(self.file_options[f].delete_original for f in files) and QMessageBox.question(
            self, "Delete originals?", f"Original files will be deleted after conversion ({len(files)} file(s)). Continue?"
        ) != QMessageBox.Yes:
            return
        for f in files:
            self.files.set_status(f, "Queued")
        self.worker = Worker(files, {f: self.file_options[f] for f in files})
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
            self.files.set_status(r.source, "Failed: " + r.error, "#c0392b")
        elif r.cancelled:
            self.files.set_status(r.source, "Cancelled", TEXT_MUTED)
        elif r.skipped:
            self.files.set_status(r.source, "Skipped (exists)", TEXT_MUTED)
        else:
            self.files.set_status(r.source, f"Done -> {r.output.name}", "#27ae60")

    def _on_done(self, results):
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self.convert_btn.setEnabled(True)
        ok = sum(1 for r in results if r.ok and not r.skipped)
        bad = sum(1 for r in results if r.error)
        self._set_status(f"Finished: {ok} converted, {bad} failed")
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
        QMessageBox.information(self, "dot.Flip", f"Right-click menu installed for {n} file types.")

    def remove_menu(self):
        from ..shell import register

        n = register.uninstall()
        QMessageBox.information(self, "dot.Flip", f"Right-click menu removed from {n} file types.")
