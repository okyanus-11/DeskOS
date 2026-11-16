"""DeskFiles filesystem operations (copy, move, rename, delete, search)."""

from __future__ import annotations

from deskos.applications.files.ops import (
    copy_items,
    create_folder,
    delete_permanently,
    directory_size,
    rename_item,
    search_files,
    unique_destination,
)


def test_copy_and_move_files_and_folders(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("hello", encoding="utf-8")
    folder = source / "folder"
    folder.mkdir()
    (folder / "inner.txt").write_text("inner", encoding="utf-8")

    destination = tmp_path / "destination"
    destination.mkdir()

    result = copy_items([str(source / "note.txt"), str(folder)], str(destination))
    assert result.ok, result.message
    assert len(result.affected or []) == 2
    assert (destination / "note.txt").read_text(encoding="utf-8") == "hello"
    assert (destination / "folder" / "inner.txt").is_file()

    move_source = tmp_path / "move-me.txt"
    move_source.write_text("move", encoding="utf-8")
    moved = copy_items([str(move_source)], str(destination), move=True)
    assert moved.ok, moved.message
    assert not move_source.exists()
    assert (destination / "move-me.txt").is_file()


def test_copy_into_same_folder_is_a_noop(tmp_path):
    source = tmp_path / "same.txt"
    source.write_text("same", encoding="utf-8")
    result = copy_items([str(source)], str(tmp_path))
    assert result.ok
    assert (tmp_path / "same.txt").read_text(encoding="utf-8") == "same"
    assert not (tmp_path / "same (2).txt").exists()


def test_copy_rejects_missing_destination(tmp_path):
    source = tmp_path / "file.txt"
    source.write_text("x", encoding="utf-8")
    result = copy_items([str(source)], str(tmp_path / "nope"))
    assert result.ok is False
    assert "not a folder" in result.message


def test_unique_destination_numbers_collisions(tmp_path):
    (tmp_path / "report.txt").write_text("1", encoding="utf-8")
    (tmp_path / "report (2).txt").write_text("2", encoding="utf-8")
    assert unique_destination(tmp_path, "report.txt").name == "report (3).txt"


def test_create_rename_and_delete(tmp_path):
    created = create_folder(str(tmp_path), "Projects")
    assert created.ok
    assert (tmp_path / "Projects").is_dir()
    duplicate = create_folder(str(tmp_path), "Projects")
    assert duplicate.ok is False

    renamed = rename_item(str(tmp_path / "Projects"), "Archive")
    assert renamed.ok
    assert (tmp_path / "Archive").is_dir()

    payload = tmp_path / "Archive" / "data.bin"
    payload.write_bytes(b"12345")
    assert directory_size(str(tmp_path / "Archive")) == 5

    deleted = delete_permanently([str(tmp_path / "Archive")])
    assert deleted.ok
    assert not (tmp_path / "Archive").exists()


def test_search_finds_nested_names(tmp_path):
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "Alpha-Report.txt").write_text("x", encoding="utf-8")
    (tmp_path / "deep" / "beta.txt").write_text("x", encoding="utf-8")
    results = search_files(str(tmp_path), "alpha")
    assert results == [str(tmp_path / "deep" / "Alpha-Report.txt")]
    assert search_files(str(tmp_path), "   ") == []


def test_copy_and_move_reject_folder_inside_itself(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "important.txt").write_text("keep me", encoding="utf-8")
    nested = source / "nested"
    nested.mkdir()

    copied = copy_items([str(source)], str(nested))
    assert copied.ok is False
    assert "subfolders" in copied.message
    assert (source / "important.txt").read_text(encoding="utf-8") == "keep me"
    assert not (nested / "project").exists()

    moved = copy_items([str(source)], str(nested), move=True)
    assert moved.ok is False
    assert (source / "important.txt").read_text(encoding="utf-8") == "keep me"
    assert source.is_dir()
