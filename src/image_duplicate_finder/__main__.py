import sys
from pathlib import Path

from image_duplicate_finder.privacy import install_runtime_guard


def main() -> int:
    install_runtime_guard()
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication

    from image_duplicate_finder.gui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Image Duplicate Finder")
    app.setOrganizationName("ImageDuplicateFinder")
    data = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    window = MainWindow(data / "reviews.sqlite3")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
