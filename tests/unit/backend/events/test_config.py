"""
Unit Tests for Events Configuration.

Tests EventsSchema loading and validation.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from modules.backend.core.config import get_app_config, load_yaml_config
from modules.backend.core.config_schema import EventsSchema, EventsStreamSchema


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """Clear lru_cache between tests so each test gets a fresh load."""
    get_app_config.cache_clear()
    yield
    get_app_config.cache_clear()


class TestEventsSchemaDefaults:
    """Test EventsSchema default values."""

    def test_transport_defaults_to_redis(self):
        schema = EventsSchema()
        assert schema.transport == "redis"

    def test_channel_prefix_defaults_to_session(self):
        schema = EventsSchema()
        assert schema.channel_prefix == "session"

    def test_dlq_enabled_defaults_to_true(self):
        schema = EventsSchema()
        assert schema.dlq_enabled is True

    def test_dlq_prefix_defaults_to_dlq(self):
        schema = EventsSchema()
        assert schema.dlq_prefix == "dlq"

    def test_consumer_timeout_defaults_to_5000(self):
        schema = EventsSchema()
        assert schema.consumer_timeout_ms == 5000

    def test_streams_defaults_to_empty_dict(self):
        schema = EventsSchema()
        assert schema.streams == {}


class TestEventsSchemaFromYaml:
    """Test EventsSchema loading from events.yaml."""

    def test_loads_from_yaml(self):
        data = load_yaml_config("events.yaml")
        schema = EventsSchema(**data)
        assert schema.transport == "redis"
        assert schema.channel_prefix == "session"
        assert "default" in schema.streams

    def test_stream_schema_from_yaml(self):
        data = load_yaml_config("events.yaml")
        schema = EventsSchema(**data)
        default_stream = schema.streams["default"]
        assert isinstance(default_stream, EventsStreamSchema)
        assert default_stream.maxlen == 10000
        assert default_stream.consumer_group == "bfa-workers"


class TestEventsSchemaStrict:
    """Test that extra='forbid' catches unknown keys."""

    def test_rejects_unknown_keys(self):
        with pytest.raises(PydanticValidationError, match="Extra inputs are not permitted"):
            EventsSchema(transport="redis", unknown_field="oops")


class TestAppConfigEvents:
    """Test that AppConfig exposes events property."""

    def test_app_config_has_events(self):
        config = get_app_config()
        assert config.events is not None
        assert isinstance(config.events, EventsSchema)

    def test_app_config_events_from_yaml(self):
        config = get_app_config()
        assert config.events.transport == "redis"
