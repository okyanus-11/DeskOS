"""Build the DeskOS desktop application with PyInstaller.

Run from the repository root, inside the virtual environment that has the
project and the ``build`` extra installed:

    pip install -e ".[build]"
    python scripts/build.py

The output is a one-folder application:

    dist/DeskOS/DeskOS(.exe)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "deskos.spec"
DIST = ROOT / "dist" / "DeskOS"



def _bundle_linux_runtime_libs(dist_dir: Path) -> list[str]:
    """Copy the Qt graphics/font libraries supplied through ``LD_LIBRARY_PATH``.

    Containers and CI images frequently provide libxkbcommon, EGL and the font
    stack outside the default loader path.  When the build runs with those
    directories on ``LD_LIBRARY_PATH``, copy the matching libraries (under the
    soname the loader expects) into ``_internal`` so the frozen application
    starts on its own.  Normal desktop builds return an empty list.
    """

    if sys.platform != "linux":
        return []
    directories = [
        Path(entry).resolve()
        for entry in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)
        if entry and Path(entry).is_dir()
    ]
    if not directories:
        return []
    internal = dist_dir / "_internal"
    if not internal.is_dir():
        return []

    patterns = (
        "libEGL*",
        "libGL.so*",
        "libGLX*",
        "libGLdispatch*",
        "libOpenGL*",
        "libxkbcommon*",
        "libfontconfig*",
        "libfreetype*",
        "libharfbuzz*",
        "libgraphite2*",
        "libpng16*",
        "libpcre2-16*",
        "libmd4c*",
        "libexpat*",
        "libb2*",
        "libbrotli*",
        "libz.so*",
    )

    copied = []
    for directory in directories:
        for pattern in patterns:
            for source in sorted(directory.glob(pattern)):
                destination = internal / source.name
                if destination.exists():
                    continue
                try:
                    real = source.resolve()
                    if not real.is_file():
                        continue
                    shutil.copyfile(real, destination)
                except OSError as exc:
                    print(f"warning: could not bundle {source.name}: {exc}", file=sys.stderr)
                    continue
                copied.append(source.name)
    return sorted(set(copied))


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

    bundled = _bundle_linux_runtime_libs(DIST)
    if bundled:
        print(f"Bundled {len(bundled)} system librar{'y' if len(bundled) == 1 else 'ies'}:")
        for name in bundled:
            print(f"  {name}")

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
