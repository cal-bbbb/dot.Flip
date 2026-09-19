from __future__ import annotations

import sys


def main(files=None) -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(files if files is not None else sys.argv[1:])
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
