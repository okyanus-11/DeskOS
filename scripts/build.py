"""Build the DeskOS desktop application with PyInstaller.

Run from the repository root, inside the virtual environment that has the
project and the ``build`` extra installed:

    pip install -e ".[build]"
    python scripts/build.py

The output is a one-folder application:

    dist/DeskOS/DeskOS(.exe)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "deskos.spec"
DIST = ROOT / "dist" / "DeskOS"


def main() -> int:
    if not SPEC.is_file():
        print(f"error: spec file not found: {SPEC}", file=sys.stderr)
        return 2
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "error: PyInstaller is not installed.\n"
            'Install the build extra first: pip install -e ".[build]"',
            file=sys.stderr,
        )
        return 2

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        str(SPEC),
    ]
    print("running:", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    executable = DIST / ("DeskOS.exe" if sys.platform == "win32" else "DeskOS")
    if not executable.exists():
        print(f"error: expected build output is missing: {executable}", file=sys.stderr)
        return 1

    print(f"\nBuilt: {executable}")
    size_mb = sum(
        path.stat().st_size for path in DIST.rglob("*") if path.is_file()
    ) / (1024 * 1024)
    print(f"Folder size: {size_mb:.1f} MiB")
    print(
        "\nThe build is unsigned. Distribute the whole folder (or a zip of it);\n"
        "copying only the executable will not work because Qt lives next to it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
