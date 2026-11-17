# Installation

## Windows installer

Download `DeskOS-Setup-1.0.0.exe` from the [latest DeskOS GitHub Release](https://github.com/okyanus-11/DeskOS/releases/latest) and follow the setup wizard. It installs per-user under `%LOCALAPPDATA%\\Programs\\DeskOS`, creates a Start Menu shortcut, offers an optional desktop shortcut, and registers a standard Windows uninstaller. Python is not required on the target PC.

The installer includes the complete PyInstaller application folder, including Qt's `_internal` runtime. Uninstalling removes the installed application and shortcuts but preserves `%APPDATA%\\DeskOS` (or the directory selected with `DESKOS_HOME`). Main-branch installers are available as 30-day GitHub Actions artifacts; tagged releases include the installer, portable Windows archive, Linux archive and SHA-256 checksums. The installer is unsigned, so Windows SmartScreen may show an unfamiliar-app warning.

## Requirements
- Windows 10/11 (primary target); Linux is supported for development
- Python 3.11 or newer
- Git

## Windows (PowerShell)

```powershell
git clone https://github.com/okyanus-11/DeskOS.git
cd DeskOS
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m deskos
```

## Linux

```bash
git clone https://github.com/okyanus-11/DeskOS.git
cd DeskOS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m deskos
```

The first launch creates local configuration, database, logs and plugin directories. On Windows, application data is stored under `%APPDATA%\DeskOS`; on Linux it uses `$XDG_DATA_HOME/DeskOS` (normally `~/.local/share/DeskOS`). Set `DESKOS_HOME` to choose another data directory.

For development and tests, install `.[dev]` or the development requirements documented in the repository, then run `python -m pytest`. See the main README for platform limitations, shortcuts and troubleshooting.
