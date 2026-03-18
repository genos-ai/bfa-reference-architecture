"""Tests for NotificationStack widget."""

import pytest

from modules.clients.tui.widgets.notification import (
    NotificationEntry,
    NotificationStack,
)


class TestNotificationStack:
    @pytest.mark.asyncio
    async def test_mounts_with_container(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield NotificationStack(id="notif-stack")

        async with TestApp().run_test() as pilot:
            stack = pilot.app.query_one("#notif-stack", NotificationStack)
            assert stack is not None
            assert stack.query_one("#notification-container", Vertical)

    @pytest.mark.asyncio
    async def test_add_notification(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield NotificationStack(id="notif-stack")

        async with TestApp().run_test() as pilot:
            stack = pilot.app.query_one("#notif-stack", NotificationStack)
            stack.add_notification("Test message", severity="info")
            await pilot.pause()

            container = stack.query_one("#notification-container", Vertical)
            assert len(container.children) == 1

    @pytest.mark.asyncio
    async def test_multiple_notifications(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield NotificationStack(id="notif-stack")

        async with TestApp().run_test() as pilot:
            stack = pilot.app.query_one("#notif-stack", NotificationStack)
            stack.add_notification("First", severity="info")
            stack.add_notification("Second", severity="warning")
            stack.add_notification("Third", severity="error")
            await pilot.pause()

            container = stack.query_one("#notification-container", Vertical)
            assert len(container.children) == 3

    @pytest.mark.asyncio
    async def test_max_visible_trimming(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield NotificationStack(id="notif-stack")

        async with TestApp().run_test() as pilot:
            stack = pilot.app.query_one("#notif-stack", NotificationStack)
            for i in range(8):
                stack.add_notification(f"Msg {i}", severity="info")
            await pilot.pause()

            container = stack.query_one("#notification-container", Vertical)
            assert len(container.children) <= NotificationStack.MAX_VISIBLE

    @pytest.mark.asyncio
    async def test_clear_all(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield NotificationStack(id="notif-stack")

        async with TestApp().run_test() as pilot:
            stack = pilot.app.query_one("#notif-stack", NotificationStack)
            stack.add_notification("One", severity="info")
            stack.add_notification("Two", severity="warning")
            await pilot.pause()

            stack.clear_all()
            await pilot.pause()

            container = stack.query_one("#notification-container", Vertical)
            assert len(container.children) == 0

    @pytest.mark.asyncio
    async def test_severity_class_applied(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield NotificationStack(id="notif-stack")

        async with TestApp().run_test() as pilot:
            stack = pilot.app.query_one("#notif-stack", NotificationStack)
            stack.add_notification("Warning!", severity="warning")
            await pilot.pause()

            entry = stack.query_one(NotificationEntry)
            assert "severity-warning" in entry.classes
