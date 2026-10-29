from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .config import default_workspace, market_packages
from .market import seed_market
from .storage import StorageError, Workspace
from .ui.main_window import MainWindow

log = logging.getLogger(__name__)


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    workspace = Workspace(default_workspace())
    try:
        added = seed_market(workspace, market_packages())
        if added:
            log.info("У Маркет додано шаблони: %s", ", ".join(added))
    except (StorageError, OSError) as e:  # Маркет не повинен заважати запуску
        log.warning("Маркет не оновлено: %s", e)
    window = MainWindow(workspace)
    window.show()
    window.start_update_check()
    return app.exec()
