"""
Unit tests for Telegram callback data factories.

Tests callback data serialization and deserialization.
"""

import pytest


class TestActionCallback:
    """Tests for ActionCallback."""

    def test_pack_and_unpack(self):
        """Test that callback data can be packed and unpacked."""
        from modules.clients.telegram.callbacks.common import ActionCallback

        original = ActionCallback(action="confirm", action_id="order_123")
        packed = original.pack()

        # Verify it's a string
        assert isinstance(packed, str)

        # Unpack and verify
        unpacked = ActionCallback.unpack(packed)
        assert unpacked.action == "confirm"
        assert unpacked.action_id == "order_123"

    def test_prefix(self):
        """Test that callback has correct prefix."""
        from modules.clients.telegram.callbacks.common import ActionCallback

        callback = ActionCallback(action="test", action_id="123")
        packed = callback.pack()

        assert packed.startswith("action:")


class TestMenuCallback:
    """Tests for MenuCallback."""

    def test_pack_and_unpack(self):
        """Test that menu callback can be packed and unpacked."""
        from modules.clients.telegram.callbacks.common import MenuCallback

        original = MenuCallback(menu="settings", item_id="user_123")
        packed = original.pack()

        unpacked = MenuCallback.unpack(packed)
        assert unpacked.menu == "settings"
        assert unpacked.item_id == "user_123"

    def test_optional_item_id(self):
        """Test that item_id is optional."""
        from modules.clients.telegram.callbacks.common import MenuCallback

        callback = MenuCallback(menu="main")
        packed = callback.pack()

        unpacked = MenuCallback.unpack(packed)
        assert unpacked.menu == "main"
        assert unpacked.item_id is None


class TestPaginationCallback:
    """Tests for PaginationCallback."""

    def test_pack_and_unpack(self):
        """Test that pagination callback can be packed and unpacked."""
        from modules.clients.telegram.callbacks.common import PaginationCallback

        original = PaginationCallback(list_type="orders", page=5, per_page=20)
        packed = original.pack()

        unpacked = PaginationCallback.unpack(packed)
        assert unpacked.list_type == "orders"
        assert unpacked.page == 5
        assert unpacked.per_page == 20

    def test_default_values(self):
        """Test that default values are applied."""
        from modules.clients.telegram.callbacks.common import PaginationCallback

        callback = PaginationCallback(list_type="items")

        assert callback.page == 0
        assert callback.per_page == 10


class TestItemCallback:
    """Tests for ItemCallback."""

    def test_pack_and_unpack(self):
        """Test that item callback can be packed and unpacked."""
        from modules.clients.telegram.callbacks.common import ItemCallback

        original = ItemCallback(action="view", item_type="order", item_id="123")
        packed = original.pack()

        unpacked = ItemCallback.unpack(packed)
        assert unpacked.action == "view"
        assert unpacked.item_type == "order"
        assert unpacked.item_id == "123"

    def test_different_actions(self):
        """Test different action types."""
        from modules.clients.telegram.callbacks.common import ItemCallback

        for action in ["view", "edit", "delete"]:
            callback = ItemCallback(action=action, item_type="test", item_id="1")
            unpacked = ItemCallback.unpack(callback.pack())
            assert unpacked.action == action
