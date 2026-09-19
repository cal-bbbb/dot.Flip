"""Install / remove the Explorer right-click "Convert to" submenu (per-user, no admin)."""
from __future__ import annotations

import subprocess
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


def windows11_menu_installed() -> bool:
    """True if the sparse package behind the Windows 11 menu is registered for this user.

    That handler also appears under "Show more options", so the classic verbs would duplicate it.
    """
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "if (Get-AppxPackage -Name DotFlip.ContextMenu) { 'yes' }"],
            capture_output=True, text=True, timeout=30, creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return "yes" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def install(extensions=None) -> int:
    """Register the classic menu for every readable image extension. Returns the number of extensions.

    Registers nothing (and removes stale verbs) when the Windows 11 package provides the menu,
    otherwise the same submenu would be listed twice.
    """
    import winreg

    if windows11_menu_installed():
        uninstall()
        return 0
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
        opts = f"{base}\\shell\\98options"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, opts) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Options")
            winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(k, "CommandFlags", 0, winreg.REG_DWORD, 0x20)  # separator above
        current = settings.get_scale()
        for pct in settings.SCALES:
            sub = f"{opts}\\shell\\{100 - pct:02d}scale{pct}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub) as k:
                mark = "  ✓" if pct == current else ""
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, f"Scale: {pct}%{mark}")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub + "\\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{prefix} --set-scale {pct}")
        more = f"{base}\\shell\\99more"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, more) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "More options...")
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
