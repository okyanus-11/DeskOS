# Building DeskOS

DeskOS is a pure-Python application. There is nothing to compile, but it can be
packaged into a self-contained Windows executable with PyInstaller.

## Development build

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
python -m deskos
```

Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
python -m deskos
```

`pip install -e .` creates the `deskos` console script, but `python -m deskos`
works straight from the source tree as well.

## Tests and the self test

```bash
QT_QPA_PLATFORM=offscreen python -m pytest
QT_QPA_PLATFORM=offscreen python -m deskos --self-test
```

The second command builds the entire application, checks the database, theme,
command registry and plugins, then exits with status 0 and prints
`DeskOS self-test: OK`. It is the quickest smoke test after a change and is used
by the build script.

On minimal Linux images Qt may be missing system libraries. The CI used for
this release extracted them into a git-ignored `.qtlibs/` directory and ran with:

```bash
export LD_LIBRARY_PATH=$PWD/.qtlibs/usr/lib/x86_64-linux-gnu:$PWD/.venv/lib/python3.12/site-packages/PySide6/Qt/lib
export FONTCONFIG_FILE=$PWD/.qtlibs/fonts.conf
export QT_QPA_PLATFORM=offscreen
```

That is an environment workaround, not a project requirement. A normal desktop
installation of PySide6 does not need it.

## Windows executable (PyInstaller)

Install the build extra and run the build script:

```powershell
.\scripts\build-windows.ps1
```

or, manually:

```powershell
pip install -e ".[build]"
python scripts\build.py
```

The spec lives in `packaging/deskos.spec` and produces a **one-folder** build:

```
dist\
  DeskOS\
    DeskOS.exe
    _internal\        # Qt, Python, assets/, plugins/
```

Output: `dist\DeskOS\DeskOS.exe`. The script prints the exact path and runs the
packaged executable with `--self-test` first when the platform allows it.

Why one-folder: Qt ships dozens of DLLs and plugin folders. One-file builds
unpack to a temporary directory on every launch (slow, and antivirus tools tend
to dislike them). Ship the folder, or zip it for distribution.

### What the spec includes

- `assets/` (SVG icons, generated PNGs, `deskos.ico`, logo)
- `plugins/` (bundled examples)
- `keyring` backends (Windows Credential Manager, Secret Service, libsecret)
- `shiboken6`
- `deskos` itself via `packaging/deskos_launcher.py`

Excluded: `tkinter`, `pytest`. The application icon is
`assets/images/deskos.ico`.

The result is unsigned. Windows SmartScreen will warn on first launch until the
executable is signed with a code-signing certificate; that step is intentionally
not automated in this repository.

## Linux binary

The same spec works on Linux (PyInstaller cannot cross-compile, so build on the
target OS):

```bash
pip install -e ".[build]"
python scripts/build.py
```

Output: `dist/DeskOS/DeskOS` (one folder). Linux packaging beyond a tarball
(AppImage, .deb) is out of scope for 1.0.

## Regenerating icons and screenshots

The SVG sources are the source of truth in `assets/icons/` and
`assets/images/deskos-logo.svg`. After changing them:

```bash
pip install PySide6
python scripts/make_icons.py
```

This renders the PNG sizes used by the UI and the `.ico` used by PyInstaller.

Screenshots in `docs/screenshots/` are rendered from the real application:

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_screenshots.py
```

The script boots DeskOS with a temporary `DESKOS_HOME`, seeds a few notes and
tasks, fills the monitor history, grabs every window and overlay, and writes
1440×900 PNGs. It never touches your own data directory. On a headless machine
the same `LD_LIBRARY_PATH` / `FONTCONFIG_FILE` workaround may be needed.

## Release checklist

1. Update `__version__` in `src/deskos/__init__.py`, the version in
   `pyproject.toml` and `CHANGELOG.md`.
2. Run the test suite and `--self-test` on Windows and Linux if possible.
3. Regenerate screenshots if the UI changed.
4. Build with `scripts/build.py` on Windows.
5. Smoke-test the packaged executable: launch, open every app, switch theme,
   open Control Centre, enable a plugin, quit and relaunch.
6. Zip `dist\DeskOS`, sign the executable if you have a certificate, publish the
   release with the changelog.
