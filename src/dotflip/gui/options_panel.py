"""Form widget generated from a Format's option schema."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QSlider, QSpinBox, QWidget
from PySide6.QtCore import Qt

from ..core.formats import Format


class OptionsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._getters: dict = {}

    def set_format(self, fmt: Format) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._getters.clear()
        if not fmt.options:
            self._form.addRow(QLabel(f"{fmt.label} has no extra options."))
            return
        for opt in fmt.options:
            if opt.kind == "int" and opt.max is not None and opt.max - (opt.min or 0) >= 50:
                w = QSlider(Qt.Horizontal)
                w.setRange(opt.min, opt.max)
                w.setValue(opt.default)
                label = QLabel(str(opt.default))
                w.valueChanged.connect(lambda v, l=label: l.setText(str(v)))
                row = QWidget()
                from PySide6.QtWidgets import QHBoxLayout

                lay = QHBoxLayout(row)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.addWidget(w, 1)
                lay.addWidget(label)
                self._form.addRow(opt.label, row)
                self._getters[opt.key] = w.value
            elif opt.kind == "int":
                w = QSpinBox()
                w.setRange(opt.min or 0, opt.max if opt.max is not None else 10_000)
                w.setValue(opt.default)
                self._form.addRow(opt.label, w)
                self._getters[opt.key] = w.value
            elif opt.kind == "bool":
                w = QCheckBox()
                w.setChecked(bool(opt.default))
                self._form.addRow(opt.label, w)
                self._getters[opt.key] = w.isChecked
            elif opt.kind == "choice":
                w = QComboBox()
                w.addItems(opt.choices)
                w.setCurrentText(str(opt.default))
                self._form.addRow(opt.label, w)
                self._getters[opt.key] = w.currentText
            else:
                w = QLineEdit(str(opt.default))
                self._form.addRow(opt.label, w)
                self._getters[opt.key] = w.text

    def values(self) -> dict:
        return {k: get() for k, get in self._getters.items()}
