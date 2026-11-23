"""Form widget generated from a Format's option schema; supports multi-file mixed-value editing."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSlider, QSpinBox, QWidget

from ..core.formats import Format
from .mixed import spin_clear_mixed_on_edit, spin_set_mixed

_MIXED = "(multi)"


class OptionsPanel(QWidget):
    changed = Signal(str, object)  # option key, new value — applies to every currently selected file

    def __init__(self, parent=None):
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)

    def set_format_message(self, text: str) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._form.addRow(QLabel(text))

    def set_format(self, fmt: Format, values: dict | None = None, mixed: frozenset = frozenset()) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        values = values or {}
        if not fmt.options:
            self._form.addRow(QLabel(f"{fmt.label} has no extra options."))
            return
        for opt in fmt.options:
            default = values.get(opt.key, opt.default)
            is_mixed = opt.key in mixed
            if opt.kind == "int" and opt.max is not None and opt.max - (opt.min or 0) >= 50:
                self._add_slider(opt, default, is_mixed)
            elif opt.kind == "int":
                self._add_spinbox(opt, default, is_mixed)
            elif opt.kind == "bool":
                self._add_checkbox(opt, default, is_mixed)
            elif opt.kind == "choice":
                self._add_combo(opt, default, is_mixed)
            else:
                self._add_text(opt, default, is_mixed)

    # ---- widget builders ----------------------------------------------
    def _add_slider(self, opt, default, is_mixed) -> None:
        w = QSlider(Qt.Horizontal)
        w.setRange(opt.min, opt.max)
        w.setValue(int(default) if default is not None else opt.min)
        label = QLabel(_MIXED if is_mixed else str(default))

        def on_change(v, l=label, k=opt.key):
            l.setText(str(v))
            self.changed.emit(k, v)

        w.valueChanged.connect(on_change)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(w, 1)
        lay.addWidget(label)
        self._form.addRow(f"{opt.label}:", row)

    def _add_spinbox(self, opt, default, is_mixed) -> None:
        w = QSpinBox()
        real_min = opt.min or 0
        w.setRange(real_min, opt.max if opt.max is not None else 10_000)
        if is_mixed:
            spin_set_mixed(w, real_min)
        else:
            w.setValue(int(default))
        def on_change(v, k=opt.key, w=w):
            spin_clear_mixed_on_edit(w)
            self.changed.emit(k, v)

        w.valueChanged.connect(on_change)
        self._form.addRow(f"{opt.label}:", w)

    def _add_checkbox(self, opt, default, is_mixed) -> None:
        w = QCheckBox()
        if is_mixed:
            w.setTristate(True)
            w.setCheckState(Qt.PartiallyChecked)
        else:
            w.setChecked(bool(default))

        def on_change(state, k=opt.key, w=w):
            if Qt.CheckState(state) == Qt.PartiallyChecked:
                return
            w.setTristate(False)
            self.changed.emit(k, w.isChecked())

        w.stateChanged.connect(on_change)
        self._form.addRow(f"{opt.label}:", w)

    def _add_combo(self, opt, default, is_mixed) -> None:
        w = QComboBox()
        w.addItems(opt.choices)
        if is_mixed:
            w.setCurrentIndex(-1)
        else:
            w.setCurrentText(str(default))
        w.currentTextChanged.connect(lambda t, k=opt.key: t and self.changed.emit(k, t))
        self._form.addRow(f"{opt.label}:", w)

    def _add_text(self, opt, default, is_mixed) -> None:
        w = QLineEdit("" if is_mixed else str(default))
        if is_mixed:
            w.setPlaceholderText(_MIXED)
        w.textChanged.connect(lambda t, k=opt.key: self.changed.emit(k, t))
        self._form.addRow(f"{opt.label}:", w)
