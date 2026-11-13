"""DeskOS entrypoint.

Usage:
    python -m deskos                # normal start
    python -m deskos --safe-mode    # start without plugins
    python -m deskos --self-test    # construct the shell, render once, exit
"""

from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from deskos import __version__
from deskos.core.config import ConfigManager
from deskos.core.logging_setup import install_exception_hook, setup_logging
from deskos.core.paths import config_path, data_dir, images_dir

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="deskos", description="DeskOS — a desktop environment companion for Windows"
    )
    parser.add_argument("--version", action="version", version=f"DeskOS {__version__}")
    parser.add_argument("--safe-mode", action="store_true", help="start without loading plugins")
    parser.add_argument(
        "--reset-config", action="store_true", help="back up and reset the configuration file"
    )
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="construct the shell, verify core services and exit",
    )
    parser.add_argument(
        "--show-data-dir", action="store_true", help="print the user data directory and exit"
    )
    return parser.parse_args(argv)


def _reset_config() -> None:
    config = ConfigManager()
    path = config_path()
    if path.is_file():
        backup = config.create_backup()
        path.unlink()
        print(f"Configuration reset. Previous settings saved to {backup}")
    else:
        print("No configuration file to reset.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.show_data_dir:
        print(data_dir())
        return 0

    setup_logging("DEBUG" if args.debug else "INFO")
    install_exception_hook()
    log.info("DeskOS %s launching (python %s)", __version__, sys.version.split()[0])

    if args.reset_config:
        _reset_config()

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationDisplayName("DeskOS")

    # Imported after QApplication exists so QNetworkAccessManager etc. are safe.
    from deskos.app import DeskOSApplication

    try:
        controller = DeskOSApplication(app, safe_mode=args.safe_mode)
    except Exception as exc:
        log.exception("DeskOS failed to start")
        headless = QGuiApplication.platformName() in ("offscreen", "minimal", "vnc")
        if headless:
            print(f"DeskOS failed to start: {exc}", file=sys.stderr)
        else:
            try:
                QMessageBox.critical(
                    None,
                    "DeskOS could not start",
                    f"DeskOS failed to start:\n\n{exc}\n\nDetails were written to the log file.",
                )
            except Exception:
                pass
        return 1

    if args.self_test:
        ok = controller.self_test()
        print("DeskOS self-test:", "OK" if ok else "FAILED")
        controller.shutdown()
        return 0 if ok else 1

    controller.start()
    if not images_dir().joinpath("deskos-256.png").is_file():
        log.warning("generated logo assets are missing; run scripts/make_icons.py")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
