# Installation

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
