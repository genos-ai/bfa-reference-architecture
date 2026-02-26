"""
Unit Tests for NoteRepository.

Tests use the real in-memory SQLite database from conftest — no mocks.
Exercises the full CRUD interface plus note-specific queries.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.exceptions import NotFoundError
from modules.backend.repositories.note import NoteRepository


@pytest.fixture
async def repo(db_session: AsyncSession) -> NoteRepository:
    """Provide a NoteRepository with a real database session."""
    return NoteRepository(db_session)


class TestCreate:
    """Tests for creating notes."""

    @pytest.mark.asyncio
    async def test_create_note(self, repo):
        note = await repo.create(title="Test Note", content="Some content")
        assert note.id is not None
        assert note.title == "Test Note"
        assert note.content == "Some content"
        assert note.is_archived is False

    @pytest.mark.asyncio
    async def test_create_note_without_content(self, repo):
        note = await repo.create(title="Title Only")
        assert note.title == "Title Only"
        assert note.content is None


class TestRead:
    """Tests for reading notes."""

    @pytest.mark.asyncio
    async def test_get_by_id(self, repo):
        note = await repo.create(title="Find Me")
        found = await repo.get_by_id(note.id)
        assert found.id == note.id
        assert found.title == "Find Me"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo):
        with pytest.raises(NotFoundError):
            await repo.get_by_id("nonexistent-id")

    @pytest.mark.asyncio
    async def test_get_by_id_or_none_found(self, repo):
        note = await repo.create(title="Maybe")
        found = await repo.get_by_id_or_none(note.id)
        assert found is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_none_missing(self, repo):
        found = await repo.get_by_id_or_none("nonexistent-id")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_all(self, repo):
        await repo.create(title="Note 1")
        await repo.create(title="Note 2")
        await repo.create(title="Note 3")
        notes = await repo.get_all()
        assert len(notes) >= 3

    @pytest.mark.asyncio
    async def test_get_all_with_limit(self, repo):
        for i in range(5):
            await repo.create(title=f"Note {i}")
        notes = await repo.get_all(limit=2)
        assert len(notes) == 2

    @pytest.mark.asyncio
    async def test_exists_true(self, repo):
        note = await repo.create(title="Exists")
        assert await repo.exists(note.id) is True

    @pytest.mark.asyncio
    async def test_exists_false(self, repo):
        assert await repo.exists("nonexistent-id") is False

    @pytest.mark.asyncio
    async def test_count(self, repo):
        initial = await repo.count()
        await repo.create(title="Counted")
        assert await repo.count() == initial + 1


class TestUpdate:
    """Tests for updating notes."""

    @pytest.mark.asyncio
    async def test_update_title(self, repo):
        note = await repo.create(title="Old Title")
        updated = await repo.update(note.id, title="New Title")
        assert updated.title == "New Title"

    @pytest.mark.asyncio
    async def test_update_not_found(self, repo):
        with pytest.raises(NotFoundError):
            await repo.update("nonexistent-id", title="Nope")


class TestDelete:
    """Tests for deleting notes."""

    @pytest.mark.asyncio
    async def test_delete_note(self, repo):
        note = await repo.create(title="Delete Me")
        await repo.delete(note.id)
        assert await repo.exists(note.id) is False

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo):
        with pytest.raises(NotFoundError):
            await repo.delete("nonexistent-id")


class TestNoteSpecific:
    """Tests for note-specific repository methods."""

    @pytest.mark.asyncio
    async def test_get_all_active_excludes_archived(self, repo):
        await repo.create(title="Active")
        archived = await repo.create(title="Archived", is_archived=True)
        active_notes = await repo.get_all_active()
        ids = [n.id for n in active_notes]
        assert archived.id not in ids

    @pytest.mark.asyncio
    async def test_get_archived(self, repo):
        await repo.create(title="Active")
        archived = await repo.create(title="Archived", is_archived=True)
        archived_notes = await repo.get_archived()
        ids = [n.id for n in archived_notes]
        assert archived.id in ids

    @pytest.mark.asyncio
    async def test_archive_note(self, repo):
        note = await repo.create(title="Archive Me")
        updated = await repo.archive(note.id)
        assert updated.is_archived is True

    @pytest.mark.asyncio
    async def test_unarchive_note(self, repo):
        note = await repo.create(title="Unarchive Me", is_archived=True)
        updated = await repo.unarchive(note.id)
        assert updated.is_archived is False

    @pytest.mark.asyncio
    async def test_search_by_title(self, repo):
        await repo.create(title="Python Guide")
        await repo.create(title="Java Guide")
        results = await repo.search_by_title("python")
        assert len(results) >= 1
        assert all("Python" in n.title for n in results)

    @pytest.mark.asyncio
    async def test_search_excludes_archived(self, repo):
        await repo.create(title="Searchable Active")
        await repo.create(title="Searchable Archived", is_archived=True)
        results = await repo.search_by_title("Searchable")
        titles = [n.title for n in results]
        assert "Searchable Active" in titles
        assert "Searchable Archived" not in titles

    @pytest.mark.asyncio
    async def test_count_active(self, repo):
        initial = await repo.count_active()
        await repo.create(title="Active Note")
        await repo.create(title="Archived Note", is_archived=True)
        assert await repo.count_active() == initial + 1
