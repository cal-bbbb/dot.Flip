"""Install / remove the Explorer right-click "Convert to" submenu (per-user, no admin)."""
from __future__ import annotations

import sys
from pathlib import Path

from .. import settings
from ..core.formats import READ_EXTENSIONS, WRITABLE

ROOT = r"Software\Classes\SystemFileAssociations"
VERB = "DotFlip"


def _command_prefix() -> str:
    """Command used to launch the CLI: the frozen exe, or pythonw -m dotflip.cli in dev."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" -m dotflip.cli'


def _delete_tree(winreg, root, path: str) -> None:
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(winreg, root, f"{path}\\{sub}")
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def install(extensions=None) -> int:
    """Register the classic menu for every readable image extension. Returns the number of extensions.

    Installed unconditionally, even when the Windows 11 package also provides the menu: the
    modern handler only appears inside File Explorer, so the classic verbs are what makes
    right-click conversion work in other apps' Open/Save dialogs and on the desktop. The
    tradeoff is that File Explorer's "Show more options" view can list "Convert to" twice
    (once from each mechanism).
    """
    import winreg

    prefix = _command_prefix()
    exts = list(extensions or READ_EXTENSIONS)
    for ext in exts:
        base = f"{ROOT}\\{ext}\\shell\\{VERB}"
        _delete_tree(winreg, winreg.HKEY_CURRENT_USER, base)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Convert to")
            winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, sys.executable)
        for i, fmt in enumerate(WRITABLE):
            sub = f"{base}\\shell\\{i:02d}{fmt.name}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, fmt.label)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub + "\\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'{prefix} --collect --to {fmt.name} "%1"')
        # Scale choices sit flat under a separator, matching the Windows 11 menu (which cannot nest).
        current = settings.get_scale()
        for n, pct in enumerate(settings.SCALES):
            sub = f"{base}\\shell\\{90 + n}scale{pct}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
                mark = "  ✓" if pct == current else ""
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, f"Scale: {pct}%{mark}")
                if n == 0:
                    winreg.SetValueEx(k, "CommandFlags", 0, winreg.REG_DWORD, 0x20)  # separator above
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub + "\\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{prefix} --set-scale {pct}")
        more = f"{base}\\shell\\99more"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, more) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "More options...")
            winreg.SetValueEx(k, "CommandFlags", 0, winreg.REG_DWORD, 0x20)  # separator above
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, more + "\\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'{prefix} --collect --gui "%1"')
    return len(exts)


def uninstall() -> int:
    import winreg

    n = 0
    for ext in READ_EXTENSIONS:
        base = f"{ROOT}\\{ext}\\shell\\{VERB}"
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, base))
        except FileNotFoundError:
            continue
        _delete_tree(winreg, winreg.HKEY_CURRENT_USER, base)
        n += 1
    return n


def is_installed() -> bool:
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{ROOT}\\.png\\shell\\{VERB}"))
        return True
    except FileNotFoundError:
        return False
