# Contributing to DeskOS

Thanks for taking the time to improve DeskOS. This guide covers the development
setup, the conventions the codebase follows, and what a good pull request looks
like.

## Before you start

- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to see how the pieces fit
  together, and [docs/PLUGIN_DEVELOPMENT.md](docs/PLUGIN_DEVELOPMENT.md) if you
  are adding a plugin.
- Search the [issue tracker](https://github.com/okyanus-11/DeskOS/issues) before
  opening a new issue.
- For anything larger than a bug fix, open an issue first so the approach can be
  agreed on before you spend time on it.

## Development setup

```bash
python3 -m venv .venv
. .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e ".[dev]"
python -m deskos
```

Run from the source tree with `python -m deskos`; the package is installed in
editable mode, so no reinstall is needed after edits.

### Headless environments

Qt needs a platform plugin. CI and containers use the offscreen backend:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest
```

Every window, dialog and widget in the test suite is exercised this way. Some
environment variables used by the tests:

| Variable | Purpose |
|---|---|
| `QT_QPA_PLATFORM=offscreen` | Render without a display server |
| `DESKOS_HOME` | Point configuration/database/logs at a scratch directory |
| `LD_LIBRARY_PATH` / `FONTCONFIG_FILE` | Only needed on minimal Linux images missing Qt's system libraries |

Never commit a `DESKOS_HOME` directory or a real `config.json`; both are in
`.gitignore`.

## Code conventions

- Python 3.11+, type hints on public functions, `from __future__ import
  annotations`.
- Keep Qt out of `core/`, `data/`, `services/` and `platform/` where possible:
  those layers are imported by tests without a `QApplication`. Widgets and
  windows live under `ui/`, `applications/` and `control_center/`.
- No global state. Services are created in `app.py` and passed through
  `DeskOSContext`.
- Long-running work goes through `deskos.utils.workers.run_async`, never a
  blocking call in a slot.
- User-visible strings are plain English today; translation hooks are not yet
  wired up, so do not add a fake `tr()` layer.
- Follow the existing theme tokens (`theme.palette`, object names such as
  `Heading`, `Muted`, `Card`) instead of hard-coded colours.
- Ruff is configured in `pyproject.toml` (line length 100). Run it if you have
  it installed; the test suite is the hard gate.

### Where things go

| Change | Location |
|---|---|
| New settings knob | `core/config.py` defaults + validation, then a Control Centre page |
| New desktop app | `applications/<name>/`, register it in `applications/catalog.py` |
| New dashboard widget | `widgets/core_widgets.py` (or a plugin) and `widgets/builtin.py` |
| Platform behaviour | `platform/base.py` contract, then `platform/windows/` and `platform/linux/` |
| Shell chrome | `ui/` (`main_window.py`, `dock.py`, `launcher.py`, `palette.py`) |
| SQLite schema change | a new migration in `core/database.py`; never edit an old one |

## Tests

```bash
QT_QPA_PLATFORM=offscreen python -m pytest
```

- Every bug fix should come with a regression test.
- New UI code should at least be constructed in `tests/test_gui.py`.
- `tests/conftest.py` provides `qapp`, `context`, `notes`, `tasks`,
  `sample_snapshot` and fake platform services. Reuse them rather than building
  a second fixture stack.
- Do not mark tests as skipped to make the suite green. If a test cannot run on
  the current platform (for example a Windows-only registry path), guard it with
  the existing fake-object pattern or `pytest.mark.windows`.

Windows-specific code should be tested on Windows when you can. If you cannot,
say so in the pull request: honesty about what was and was not executed is more
valuable than a green badge.

## Pull requests

1. Fork the repository and create a topic branch.
2. Keep the change focused; unrelated refactors belong in a separate PR.
3. Update the documentation when behaviour changes (README, `docs/`, CHANGELOG).
4. Run the test suite and paste the result in the PR description.
5. Describe **why** the change is needed, not only what changed, and list any
   manual checks you performed (especially on Windows).

Commit messages are short and imperative, for example:

```
Fix the control centre crash when opening the network page
```

Do not force-push a branch other people may have based work on, and do not
commit generated data: `.venv/`, `dist/`, `release/`, `*.db`, logs and
`config.json` are ignored for a reason.

## Adding a plugin

Plugins are the preferred way to extend DeskOS. A plugin needs:

- a folder under `plugins/` (bundled) or `<data dir>/plugins/` (user),
- `plugin.json` with `id`, `name`, `version`, `api_version: 1` and `entry`,
- a `register(api)` function in the entry module,
- declared permissions for every API call it makes.

See [docs/PLUGIN_DEVELOPMENT.md](docs/PLUGIN_DEVELOPMENT.md) for the API, the
permission list and a complete example. Plugins run in-process: do not add
network calls or timers that outlive the widget they belong to, and clean up in
`api.cleanup()`.

## Security

- Never commit credentials, tokens, signing keys or personal paths.
- DeskAI keys belong in the OS credential store, never in `config.json`, logs or
  a commit.
- Plugins are not sandboxed; call that out in your plugin's README if it talks
  to the network.

## License

By contributing you agree that your work is licensed under the MIT License used
by this project.
