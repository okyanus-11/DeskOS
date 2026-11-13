"""DeskFiles: browse, search, copy, move, rename, delete and inspect files."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileSystemModel,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from deskos.applications.base import AppPage
from deskos.applications.files.ops import (
    copy_items,
    create_folder,
    delete_permanently,
    directory_size,
    humanize_mode,
    rename_item,
    search_files,
    unique_destination,
)
from deskos.ui.components import IconButton, Muted, SearchField, SectionTitle, apply_shadow
from deskos.ui.dialogs import PromptDialog
from deskos.utils.formatting import format_bytes
from deskos.utils.workers import run_async

log = logging.getLogger(__name__)


class PropertiesDialog(QDialog):
    def __init__(self, parent: QWidget, path: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Properties — {Path(path).name}")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        heading = QLabel(Path(path).name)
        heading.setObjectName("Subheading")
        layout.addWidget(heading)
        layout.addWidget(Muted(path))
        layout.addSpacing(6)

        try:
            stat = os.stat(path)
            info = [
                ("Type", "Folder" if os.path.isdir(path) else (Path(path).suffix or "File")),
                ("Size", format_bytes(stat.st_size) if not os.path.isdir(path) else "Calculating…"),
                ("Modified", datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y, %H:%M")),
                ("Created", datetime.fromtimestamp(stat.st_ctime).strftime("%d %b %Y, %H:%M")),
                ("Permissions", humanize_mode(path)),
            ]
        except OSError as exc:
            info = [("Error", str(exc))]

        for label, value in info:
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("StatLabel")
            name.setFixedWidth(110)
            row.addWidget(name)
            row.addWidget(QLabel(value), 1)
            layout.addLayout(row)

        close = QPushButton("Close")
        close.setObjectName("PrimaryButton")
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close)
        layout.addLayout(footer)

        if os.path.isdir(path):
            run_async(directory_size, self._apply_size, path=path)

    def _apply_size(self, size: int) -> None:
        for label in self.findChildren(QLabel):
            if label.text() == "Calculating…":
                label.setText(format_bytes(size))


class FilesPage(AppPage):
    def __init__(self, context, parent: QWidget | None = None) -> None:
        super().__init__(context, parent)
        self._history: list[str] = []
        self._history_index = -1
        self._clipboard: list[str] = []
        self._clipboard_cut = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(280)
        self._search_timer.timeout.connect(self._run_search)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 6, 18, 16)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.back_button = IconButton(self.icons, "chevron-left", "Back", 30, 16)
        self.back_button.clicked.connect(lambda: self._go_history(-1))
        self.forward_button = IconButton(self.icons, "chevron-right", "Forward", 30, 16)
        self.forward_button.clicked.connect(lambda: self._go_history(1))
        self.up_button = IconButton(self.icons, "arrow-up", "Up one level", 30, 16)
        self.up_button.clicked.connect(self._go_up)
        self.refresh_button = IconButton(self.icons, "refresh", "Refresh", 30, 16)
        self.refresh_button.clicked.connect(self._refresh)
        for button in (self.back_button, self.forward_button, self.up_button, self.refresh_button):
            toolbar.addWidget(button)

        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("Path")
        self.path_field.returnPressed.connect(self._on_path_entered)
        toolbar.addWidget(self.path_field, 1)

        self.search = SearchField(self.icons, "Search this folder…")
        self.search.setMinimumWidth(230)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        toolbar.addWidget(self.search)

        self.new_folder_button = IconButton(self.icons, "plus", "New folder", 30, 16)
        self.new_folder_button.clicked.connect(self._new_folder)
        toolbar.addWidget(self.new_folder_button)
        self.delete_button = IconButton(self.icons, "trash", "Delete", 30, 16)
        self.delete_button.clicked.connect(self._delete_selection)
        toolbar.addWidget(self.delete_button)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 6, 0)
        sidebar_layout.setSpacing(6)
        sidebar_layout.addWidget(SectionTitle("Quick access"))
        self.locations = QListWidget()
        self.locations.setIconSize(QSize(16, 16))
        self.locations.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.locations.itemClicked.connect(self._on_location_clicked)
        sidebar_layout.addWidget(self.locations, 1)
        sidebar_layout.addWidget(SectionTitle("Drives"))
        self.drives = QListWidget()
        self.drives.setIconSize(QSize(16, 16))
        self.drives.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.drives.itemClicked.connect(self._on_location_clicked)
        sidebar_layout.addWidget(self.drives, 1)
        splitter.addWidget(sidebar)

        browser = QWidget()
        browser_layout = QVBoxLayout(browser)
        browser_layout.setContentsMargins(6, 0, 0, 0)
        browser_layout.setSpacing(6)
        self.model = QFileSystemModel(self)
        self.model.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs
        )
        self.model.setReadOnly(False)
        self.home = self.ctx.platform.files.default_path()
        self.model.setRootPath(self.home)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.home))
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setAlternatingRowColors(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.doubleClicked.connect(self._on_double_click)
        for column in (1, 2, 3):
            self.tree.setColumnWidth(column, 120)
        browser_layout.addWidget(self.tree, 1)

        self.results = QListWidget()
        self.results.setIconSize(QSize(16, 16))
        self.results.itemDoubleClicked.connect(self._on_result_open)
        self.results.hide()
        self.results_status = Muted("")
        self.results_status.hide()
        browser_layout.addWidget(self.results_status)
        browser_layout.addWidget(self.results, 1)
        splitter.addWidget(browser)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 760])
        root.addWidget(splitter, 1)

        self.status = Muted("")
        root.addWidget(self.status)

        for label, path in self.ctx.platform.files.locations():
            item = QListWidgetItem(self.icons.icon("folder", 16, self.theme.accent), label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.locations.addItem(item)
        for label, path in self.ctx.platform.files.drives():
            item = QListWidgetItem(self.icons.icon("storage", 16, self.theme.palette.subtext1), label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.drives.addItem(item)

        self.navigate(self.home)

    # ------------------------------------------------------------ navigation
    def navigate(self, path: str, *, record: bool = True) -> None:
        target = Path(path).expanduser()
        if not target.exists():
            self.ctx.toast(f"Path not found: {path}")
            return
        if not target.is_dir():
            self.ctx.platform.files.open_path(str(target))
            return
        resolved = str(target)
        self.path_field.setText(resolved)
        index = self.model.index(resolved)
        if not index.isValid():
            return
        self.tree.setRootIndex(index)
        self.model.setRootPath(resolved)
        if record:
            self._history = self._history[: self._history_index + 1]
            self._history.append(resolved)
            self._history_index = len(self._history) - 1
        self._update_nav_state()
        self.status.setText("")

    def _update_nav_state(self) -> None:
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(self._history_index < len(self._history) - 1)
        self.up_button.setEnabled(Path(self.current_path()).parent != Path(self.current_path()))

    def current_path(self) -> str:
        return self.path_field.text() or self.home

    def _go_history(self, delta: int) -> None:
        target = self._history_index + delta
        if 0 <= target < len(self._history):
            self._history_index = target
            self.navigate(self._history[target], record=False)

    def _go_up(self) -> None:
        parent = Path(self.current_path()).parent
        if str(parent) != self.current_path():
            self.navigate(str(parent))

    def _refresh(self) -> None:
        self.model.setRootPath("")
        self.navigate(self.current_path(), record=False)

    def _on_path_entered(self) -> None:
        self.navigate(self.path_field.text())

    def _on_location_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.navigate(str(path))

    def _on_double_click(self, index: QModelIndex) -> None:
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.navigate(path)
        else:
            self.ctx.platform.files.open_path(path)

    # ---------------------------------------------------------------- search
    def _run_search(self) -> None:
        query = self.search.text().strip()
        if not query:
            self.results.hide()
            self.results_status.hide()
            self.tree.show()
            return
        self.tree.hide()
        self.results.show()
        self.results_status.show()
        self.results_status.setText(f"Searching “{query}” in {self.current_path()}…")
        self.results.clear()
        run_async(
            search_files,
            self._on_search_results,
            lambda message: self.results_status.setText(f"Search failed: {message}"),
            root=self.current_path(),
            query=query,
        )

    def _on_search_results(self, paths: list[str]) -> None:
        self.results.clear()
        for path in paths:
            icon = (
                self.icons.icon("folder", 16, self.theme.accent)
                if Path(path).is_dir()
                else self.icons.icon_for_path(path)
            )
            item = QListWidgetItem(icon, path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.results.addItem(item)
        if paths:
            self.results_status.setText(f"{len(paths)} results")
        else:
            self.results_status.setText("No matching files in this folder")

    def _on_result_open(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if Path(path).is_dir():
            self.search.clear()
            self.tree.show()
            self.navigate(path)
        else:
            self.ctx.platform.files.open_path(path)

    # --------------------------------------------------------------- actions
    def _selected_paths(self) -> list[str]:
        indexes = self.tree.selectionModel().selectedRows() if self.tree.selectionModel() else []
        if not indexes:
            indexes = self.tree.selectionModel().selectedIndexes() if self.tree.selectionModel() else []
        paths: list[str] = []
        for index in indexes:
            path = self.model.filePath(index)
            if path and path not in paths:
                paths.append(path)
        return paths

    def _tree_menu(self, position) -> None:
        paths = self._selected_paths()
        menu = QMenu(self)
        menu.addAction(self.icons.icon("external", 16), "Open", self._open_selection)
        menu.addAction(self.icons.icon("folder", 16), "Show in file manager", self._reveal_selection)
        menu.addSeparator()
        menu.addAction(self.icons.icon("copy", 16), "Copy", lambda: self._clipboard_set(cut=False))
        menu.addAction(self.icons.icon("cut", 16), "Cut", lambda: self._clipboard_set(cut=True))
        paste = menu.addAction(self.icons.icon("paste", 16), "Paste", self._paste)
        paste.setEnabled(bool(self._clipboard))
        menu.addSeparator()
        menu.addAction(self.icons.icon("edit", 16), "Rename", self._rename_selection)
        menu.addAction(self.icons.icon("trash", 16), "Delete", self._delete_selection)
        menu.addSeparator()
        menu.addAction(self.icons.icon("plus", 16), "New folder", self._new_folder)
        menu.addAction(self.icons.icon("info", 16), "Properties", self._show_properties)
        if not paths:
            for action in menu.actions()[:5]:
                action.setEnabled(False)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _open_selection(self) -> None:
        for path in self._selected_paths():
            if Path(path).is_dir():
                self.navigate(path)
                break
            self.ctx.platform.files.open_path(path)

    def _reveal_selection(self) -> None:
        for path in self._selected_paths()[:1]:
            self.ctx.platform.files.reveal_path(path)

    def _clipboard_set(self, *, cut: bool) -> None:
        self._clipboard = self._selected_paths()
        self._clipboard_cut = cut
        if self._clipboard:
            action = "Cut" if cut else "Copied"
            self.ctx.toast(f"{action} {len(self._clipboard)} item(s)")

    def _paste(self) -> None:
        if not self._clipboard:
            return
        result = copy_items(self._clipboard, self.current_path(), move=self._clipboard_cut)
        if result.ok:
            self.ctx.toast("Paste complete")
            self._clipboard = []
        else:
            QMessageBox.warning(self, "Paste failed", result.message)
        self._refresh()

    def _rename_selection(self) -> None:
        paths = self._selected_paths()
        if len(paths) != 1:
            self.ctx.toast("Select a single item to rename")
            return
        current = Path(paths[0])
        dialog = PromptDialog(
            self,
            "Rename",
            f"New name for “{current.name}”",
            text=current.name,
            confirm_label="Rename",
        )
        if dialog.exec() and dialog.value() and dialog.value() != current.name:
            result = rename_item(str(current), dialog.value())
            if not result.ok:
                QMessageBox.warning(self, "Rename failed", result.message)
            self._refresh()

    def _new_folder(self) -> None:
        dialog = PromptDialog(
            self,
            "New folder",
            f"Create a folder in {self.current_path()}",
            placeholder="Folder name",
            confirm_label="Create",
        )
        if dialog.exec() and dialog.value():
            result = create_folder(self.current_path(), dialog.value())
            if not result.ok:
                QMessageBox.warning(self, "Could not create folder", result.message)
            self._refresh()

    def _delete_selection(self) -> None:
        paths = self._selected_paths()
        if not paths:
            return
        names = ", ".join(Path(path).name for path in paths[:4])
        answer = QMessageBox.question(
            self,
            "Move to trash",
            f"Move {len(paths)} item(s) to the trash?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        failed: list[str] = []
        for path in paths:
            if not self.ctx.platform.files.trash(path):
                failed.append(path)
        if failed:
            answer = QMessageBox.question(
                self,
                "Trash unavailable",
                f"{len(failed)} item(s) could not be moved to the trash. Delete permanently?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                result = delete_permanently(failed)
                if not result.ok:
                    QMessageBox.warning(self, "Delete failed", result.message)
        self._refresh()

    def _show_properties(self) -> None:
        paths = self._selected_paths()
        if len(paths) != 1:
            self.ctx.toast("Select a single item for properties")
            return
        dialog = PropertiesDialog(self, paths[0])
        apply_shadow(dialog, 40, 10, 110)
        dialog.exec()
