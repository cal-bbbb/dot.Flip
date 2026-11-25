from __future__ import annotations

import sys


def _claim_app_identity() -> None:
    """Give this process its own taskbar identity/icon.

    Needed because a process launched via the right-click menu's "More options" can inherit
    the AppUserModelID of the packaged COM surrogate that spawned it, which makes Windows show
    that package's identity (and icon) on the taskbar instead of this window's own.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dotFlip.ImageConverter")
    except (AttributeError, OSError):
        pass


def main(files=None) -> int:
    _claim_app_identity()

    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow
    from .theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    win = MainWindow(files if files is not None else sys.argv[1:])
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
