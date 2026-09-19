r"""Small per-user settings shared by the CLI, the classic menu and the Windows 11 shell extension.

Stored in HKCU\Software\DotFlip so the C++ extension can read the current value (to show a check mark).
"""
from __future__ import annotations

KEY = r"Software\DotFlip"
SCALES = (100, 50)  # percent choices offered by the right-click "Options" menu


def get_scale() -> int:
    """Scale (percent) applied to right-click conversions. Defaults to 100."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            value, _ = winreg.QueryValueEx(k, "Scale")
        return value if value in SCALES else 100
    except (ImportError, OSError):
        return 100


def set_scale(percent: int) -> None:
    if percent not in SCALES:
        raise ValueError(f"Scale must be one of {SCALES}")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        winreg.SetValueEx(k, "Scale", 0, winreg.REG_DWORD, percent)
