"""Unit tests for settings panel routing (menu navigation)."""

from __future__ import annotations


class TestSettingsMenuConfig:
    """Tests for settings menu item configuration and routing keys."""

    EXPECTED_PANELS = [
        "appearance",
        "permission",
        "router",
        "vector_backend",
        "system_prompt",
        "update",
        "env_status",
        "log_viewer",
        "language",
        "about",
    ]

    def test_all_expected_panels_defined(self):
        """Ensure all expected panel IDs are present in the menu config."""
        from misaka.ui.settings.pages.settings_page import _MENU_ITEMS

        panel_ids = [item_id for item_id, _, _ in _MENU_ITEMS]
        for expected in self.EXPECTED_PANELS:
            assert expected in panel_ids, f"Missing panel: {expected}"

    def test_menu_items_have_labels_and_icons(self):
        """Each menu item must have an i18n key and icon."""
        from misaka.ui.settings.pages.settings_page import _MENU_ITEMS

        for item_id, i18n_key, icon in _MENU_ITEMS:
            assert item_id, "Panel ID must not be empty"
            assert i18n_key, f"i18n key missing for {item_id}"
            assert icon is not None, f"Icon missing for {item_id}"

    def test_no_duplicate_panel_ids(self):
        """Panel IDs must be unique."""
        from misaka.ui.settings.pages.settings_page import _MENU_ITEMS

        ids = [item_id for item_id, _, _ in _MENU_ITEMS]
        assert len(ids) == len(set(ids))
