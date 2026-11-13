"""PyInstaller entry point.

Keeping a tiny launcher outside the package avoids freezing a module that is
also importable as ``deskos.main`` (PyInstaller treats the script as the program
entry, not as a package module).
"""

from __future__ import annotations

import sys

from deskos.main import main

if __name__ == "__main__":
    sys.exit(main())
