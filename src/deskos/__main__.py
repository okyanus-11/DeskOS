"""Allow ``python -m deskos``."""

from __future__ import annotations

import sys

from deskos.main import main

if __name__ == "__main__":
    sys.exit(main())
