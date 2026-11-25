"""Helpers for showing a "mixed values" state on spin boxes during multi-file bulk editing.

QComboBox (setCurrentIndex(-1)), QLineEdit (blank text) and QCheckBox (Qt.PartiallyChecked, via
setTristate) all support a blank/mixed state natively. QSpinBox/QDoubleSpinBox don't, so these
reserve one extra step below the real minimum and show ``specialValueText`` there instead.
"""
from __future__ import annotations

_MIXED_TEXT = "(multi)"


def _step(box) -> float:
    return 1 if type(box).__name__ == "QSpinBox" else box.singleStep() or 1


def spin_set_mixed(box, real_min) -> None:
    """Show the box as "(multi)". ``real_min`` is the field's normal minimum."""
    box.setProperty("_real_min", real_min)
    box.setMinimum(real_min - _step(box))
    box.setSpecialValueText(_MIXED_TEXT)
    box.setValue(box.minimum())


def spin_set_value(box, value) -> None:
    """Show a real value, clearing any mixed-state sentinel left over from a previous selection."""
    real_min = box.property("_real_min")
    if real_min is not None:
        box.setSpecialValueText("")
        box.setMinimum(real_min)
        box.setProperty("_real_min", None)
    box.setValue(value)


def spin_clear_mixed_on_edit(box) -> None:
    """Call first in a valueChanged handler: drops the sentinel once the user picks a real value."""
    if box.property("_real_min") is not None:
        real_min = box.property("_real_min")
        box.setSpecialValueText("")
        box.setMinimum(real_min)
        box.setProperty("_real_min", None)
