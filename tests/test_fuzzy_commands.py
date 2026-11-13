"""Fuzzy search and the command registry."""

from __future__ import annotations

from deskos.core.commands import (
    CATEGORY_APPS,
    CATEGORY_SYSTEM,
    Command,
    CommandRegistry,
)
from deskos.utils.fuzzy import filter_items, fuzzy_score


class TestFuzzy:
    def test_exact_prefix_scores_highest(self):
        exact = fuzzy_score("term", "Terminal")
        scattered = fuzzy_score("term", "Temporary reminder message")
        assert exact is not None and scattered is not None
        assert exact > scattered

    def test_no_match_returns_none(self):
        assert fuzzy_score("zzz", "Terminal") is None

    def test_empty_query_matches_everything(self):
        assert fuzzy_score("", "anything") == 0

    def test_ranking_and_filtering(self):
        items = ["Open terminal", "Open text editor", "Show system status"]
        ranked = filter_items("term", items)
        assert ranked[0] == "Open terminal"
        assert "Show system status" not in ranked

    def test_abbreviation_matching(self):
        assert fuzzy_score("st", "System status") is not None


class TestCommandRegistry:
    def _registry(self) -> CommandRegistry:
        registry = CommandRegistry()
        registry.register_many(
            [
                Command(
                    id="app.terminal",
                    title="Open terminal",
                    category=CATEGORY_APPS,
                    keywords=("shell", "powershell"),
                    callback=lambda: "opened",
                ),
                Command(
                    id="system.cpu",
                    title="Show CPU usage",
                    category=CATEGORY_SYSTEM,
                    callback=lambda: (_ for _ in ()).throw(RuntimeError("cpu broke")),
                ),
            ]
        )
        return registry

    def test_search_by_title_and_keyword(self):
        registry = self._registry()
        assert registry.search("terminal")[0].id == "app.terminal"
        assert registry.search("powershell")[0].id == "app.terminal"
        assert registry.search("cpu")[0].id == "system.cpu"
        assert registry.search("no such thing") == []

    def test_all_and_categories(self):
        registry = self._registry()
        assert [command.id for command in registry.all()] == ["app.terminal", "system.cpu"]
        assert registry.categories() == [CATEGORY_APPS, CATEGORY_SYSTEM]

    def test_execute_success_and_error_isolation(self):
        registry = self._registry()
        ok = registry.execute("app.terminal")
        assert ok.ok and ok.value == "opened"
        failed = registry.execute("system.cpu")
        assert failed.ok is False
        assert "cpu broke" in failed.error
        unknown = registry.execute("does.not.exist")
        assert unknown.ok is False

    def test_unregister_and_listener(self):
        registry = self._registry()
        changes: list[int] = []
        registry.add_listener(lambda: changes.append(1))
        registry.unregister("app.terminal")
        assert registry.get("app.terminal") is None
        assert changes
        registry.unregister_prefix("system.")
        assert registry.all() == []

    def test_duplicate_registration_replaces(self):
        registry = self._registry()
        registry.register(Command(id="system.cpu", title="CPU again", callback=lambda: 1))
        assert registry.get("system.cpu").title == "CPU again"
        assert len(registry.all()) == 2
