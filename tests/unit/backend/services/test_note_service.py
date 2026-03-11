"""
Tests for Note Service.

Tests NoteService business logic against a real database session.
Mock only what we don't operate (nothing here — pure DB tests).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.exceptions import NotFoundError
from modules.backend.schemas.note import NoteCreate, NoteUpdate
from modules.backend.services.note import NoteService


@pytest.fixture
def service(db_session: AsyncSession) -> NoteService:
    """NoteService wired to a real test database session."""
    return NoteService(db_session)


class TestNoteServiceCreate:
    """Tests for note creation."""

    @pytest.mark.asyncio
    async def test_create_note_success(self, service):
        """Should persist a note and return it with a generated ID."""
        data = NoteCreate(title="Test Note", content="Test content")
        note = await service.create_note(data)

        assert note.id is not None
        assert note.title == "Test Note"
        assert note.content == "Test content"
        assert note.is_archived is False

    @pytest.mark.asyncio
    async def test_create_note_without_content(self, service):
        """Should create a note with only a title."""
        data = NoteCreate(title="Title Only")
        note = await service.create_note(data)

        assert note.id is not None
        assert note.title == "Title Only"
        assert note.content is None

    @pytest.mark.asyncio
    async def test_created_note_is_retrievable(self, service):
        """Created note should be fetchable by ID."""
        data = NoteCreate(title="Retrievable", content="Check")
        created = await service.create_note(data)

        fetched = await service.get_note(created.id)
        assert fetched.id == created.id
        assert fetched.title == "Retrievable"


class TestNoteServiceGet:
    """Tests for getting notes."""

    @pytest.mark.asyncio
    async def test_get_note_success(self, service):
        """Should return the correct note by ID."""
        data = NoteCreate(title="Found Note", content="Body")
        created = await service.create_note(data)

        result = await service.get_note(created.id)
        assert result.id == created.id
        assert result.title == "Found Note"

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, service):
        """Should raise NotFoundError for nonexistent ID."""
        with pytest.raises(NotFoundError):
            await service.get_note("nonexistent-id")


class TestNoteServiceList:
    """Tests for listing notes."""

    @pytest.mark.asyncio
    async def test_list_notes_active_only(self, service):
        """Should list only non-archived notes by default."""
        await service.create_note(NoteCreate(title="Active"))
        archived = await service.create_note(NoteCreate(title="Archived"))
        await service.archive_note(archived.id)

        result = await service.list_notes()
        titles = [n.title for n in result]
        assert "Active" in titles
        assert "Archived" not in titles

    @pytest.mark.asyncio
    async def test_list_notes_include_archived(self, service):
        """Should include archived notes when requested."""
        await service.create_note(NoteCreate(title="Active"))
        archived = await service.create_note(NoteCreate(title="Archived"))
        await service.archive_note(archived.id)

        result = await service.list_notes(include_archived=True)
        titles = [n.title for n in result]
        assert "Active" in titles
        assert "Archived" in titles

    @pytest.mark.asyncio
    async def test_list_notes_with_pagination(self, service):
        """Should respect limit and offset parameters."""
        for i in range(5):
            await service.create_note(NoteCreate(title=f"Note {i}"))

        result = await service.list_notes(limit=2, offset=0)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_notes_paginated_returns_total(self, service):
        """Paginated listing should return total count."""
        for i in range(3):
            await service.create_note(NoteCreate(title=f"Note {i}"))

        notes, total = await service.list_notes_paginated(limit=2, offset=0)
        assert len(notes) == 2
        assert total == 3


class TestNoteServiceUpdate:
    """Tests for updating notes."""

    @pytest.mark.asyncio
    async def test_update_note_title(self, service):
        """Should update the title and persist it."""
        created = await service.create_note(NoteCreate(title="Original"))

        data = NoteUpdate(title="Updated Title")
        result = await service.update_note(created.id, data)

        assert result.title == "Updated Title"

        # Verify persistence
        fetched = await service.get_note(created.id)
        assert fetched.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_note_multiple_fields(self, service):
        """Should update multiple fields at once."""
        created = await service.create_note(
            NoteCreate(title="Old", content="Old content"),
        )

        data = NoteUpdate(title="New", content="New content", is_archived=True)
        result = await service.update_note(created.id, data)

        assert result.title == "New"
        assert result.content == "New content"
        assert result.is_archived is True

    @pytest.mark.asyncio
    async def test_update_note_no_changes(self, service):
        """Should return existing note when no fields provided."""
        created = await service.create_note(NoteCreate(title="Unchanged"))

        data = NoteUpdate()  # No fields set
        result = await service.update_note(created.id, data)

        assert result.id == created.id
        assert result.title == "Unchanged"

    @pytest.mark.asyncio
    async def test_update_nonexistent_note_raises(self, service):
        """Should raise NotFoundError for nonexistent ID."""
        data = NoteUpdate(title="Won't work")
        with pytest.raises(NotFoundError):
            await service.update_note("nonexistent-id", data)


class TestNoteServiceDelete:
    """Tests for deleting notes."""

    @pytest.mark.asyncio
    async def test_delete_note_success(self, service):
        """Should remove the note from the database."""
        created = await service.create_note(NoteCreate(title="To Delete"))

        await service.delete_note(created.id)

        with pytest.raises(NotFoundError):
            await service.get_note(created.id)

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, service):
        """Should raise NotFoundError for nonexistent ID."""
        with pytest.raises(NotFoundError):
            await service.delete_note("nonexistent-id")


class TestNoteServiceArchive:
    """Tests for archiving notes."""

    @pytest.mark.asyncio
    async def test_archive_note(self, service):
        """Should set is_archived to True."""
        created = await service.create_note(NoteCreate(title="To Archive"))

        result = await service.archive_note(created.id)
        assert result.is_archived is True

        # Verify persistence
        fetched = await service.get_note(created.id)
        assert fetched.is_archived is True

    @pytest.mark.asyncio
    async def test_unarchive_note(self, service):
        """Should set is_archived back to False."""
        created = await service.create_note(NoteCreate(title="To Unarchive"))
        await service.archive_note(created.id)

        result = await service.unarchive_note(created.id)
        assert result.is_archived is False

    @pytest.mark.asyncio
    async def test_archive_nonexistent_raises(self, service):
        """Should raise NotFoundError for nonexistent ID."""
        with pytest.raises(NotFoundError):
            await service.archive_note("nonexistent-id")


class TestNoteServiceSearch:
    """Tests for searching notes."""

    @pytest.mark.asyncio
    async def test_search_notes_by_title(self, service):
        """Should find notes matching the query (case-insensitive)."""
        await service.create_note(NoteCreate(title="Python Guide"))
        await service.create_note(NoteCreate(title="Java Guide"))
        await service.create_note(NoteCreate(title="Unrelated"))

        result = await service.search_notes("guide")
        titles = [n.title for n in result]
        assert "Python Guide" in titles
        assert "Java Guide" in titles
        assert "Unrelated" not in titles

    @pytest.mark.asyncio
    async def test_search_notes_excludes_archived(self, service):
        """Search should not return archived notes."""
        await service.create_note(NoteCreate(title="Active Guide"))
        archived = await service.create_note(NoteCreate(title="Archived Guide"))
        await service.archive_note(archived.id)

        result = await service.search_notes("guide")
        titles = [n.title for n in result]
        assert "Active Guide" in titles
        assert "Archived Guide" not in titles

    @pytest.mark.asyncio
    async def test_search_notes_with_limit(self, service):
        """Should respect the limit parameter."""
        for i in range(5):
            await service.create_note(NoteCreate(title=f"Match {i}"))

        result = await service.search_notes("Match", limit=2)
        assert len(result) == 2
