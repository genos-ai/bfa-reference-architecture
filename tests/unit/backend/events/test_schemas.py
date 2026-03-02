"""
Unit Tests for Domain Event Envelope.

Tests EventEnvelope serialization, defaults, and Tier 4 field presence.
"""

import json
import uuid

import pytest

from modules.backend.events.schemas import EventEnvelope


class TestEventEnvelopeDefaults:
    """Test that EventEnvelope auto-generates required fields."""

    def test_event_id_is_auto_generated(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.event_id
        uuid.UUID(event.event_id)

    def test_timestamp_is_populated(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.timestamp
        assert "T" in event.timestamp

    def test_event_version_defaults_to_one(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.event_version == 1

    def test_correlation_id_is_auto_generated(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.correlation_id
        uuid.UUID(event.correlation_id)

    def test_payload_defaults_to_empty_dict(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.payload == {}


class TestEventEnvelopeRoundtrip:
    """Test serialization/deserialization roundtrip."""

    def test_dict_roundtrip(self):
        event = EventEnvelope(
            event_type="notes.note.created",
            source="note-service",
            payload={"note_id": "abc", "title": "Hello"},
        )
        data = event.model_dump()
        restored = EventEnvelope(**data)
        assert restored.event_id == event.event_id
        assert restored.event_type == event.event_type
        assert restored.source == event.source
        assert restored.payload == event.payload

    def test_json_roundtrip(self):
        event = EventEnvelope(
            event_type="notes.note.created",
            source="note-service",
            payload={"count": 42},
        )
        json_str = event.model_dump_json()
        data = json.loads(json_str)
        restored = EventEnvelope(**data)
        assert restored.event_type == event.event_type
        assert restored.payload["count"] == 42


class TestEventEnvelopeTier4Fields:
    """Test Tier 4 fields are present and optional where expected."""

    def test_session_id_is_optional(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.session_id is None

    def test_session_id_can_be_set(self):
        sid = str(uuid.uuid4())
        event = EventEnvelope(
            event_type="test.event", source="test", session_id=sid
        )
        assert event.session_id == sid

    def test_trace_id_is_optional(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.trace_id is None

    def test_trace_id_can_be_set(self):
        event = EventEnvelope(
            event_type="test.event", source="test", trace_id="abc123"
        )
        assert event.trace_id == "abc123"

    def test_correlation_id_always_present(self):
        event = EventEnvelope(event_type="test.event", source="test")
        assert event.correlation_id is not None
