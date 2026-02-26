"""
Unit Tests for QA Compliance Agent (code.qa.agent).

Service tests use real temporary files — no mocks.
Schema tests validate output models.
Config tests verify YAML loading.
"""

import textwrap
from pathlib import Path

import pytest

from modules.backend.agents.coordinator.registry import get_registry
from modules.backend.agents.deps.base import FileScope
from modules.backend.agents.schemas import QaAuditResult, Violation
from modules.backend.services.compliance import ComplianceScannerService


@pytest.fixture
def qa_config():
    """Load the real QA agent config from the registry."""
    return get_registry().get("code.qa.agent")


@pytest.fixture
def project_with_violations(tmp_path):
    """Create a temporary project with known violations for scanner testing."""
    modules_dir = tmp_path / "modules" / "example"
    modules_dir.mkdir(parents=True)
    (modules_dir / "__init__.py").write_text("")

    (modules_dir / "bad_imports.py").write_text(textwrap.dedent("""\
        import logging
        from .sibling import something
        import os
        val = os.getenv("KEY", "fallback_default")
    """))

    (modules_dir / "bad_datetime.py").write_text(textwrap.dedent("""\
        from modules.backend.core.utils import utc_now
        from datetime import datetime
        now = datetime.now()
        utc = datetime.utcnow()
    """))

    (modules_dir / "hardcoded.py").write_text(textwrap.dedent("""\
        MAX_RETRIES = 3
        TIMEOUT_SECONDS = 30
        API_VERSION = "v2"
        __version__ = "1.0.0"
        __all__ = ["something"]
        normal_var = 42
    """))

    (modules_dir / "clean.py").write_text(textwrap.dedent("""\
        from modules.backend.core.logging import get_logger
        from modules.backend.core.utils import utc_now
        logger = get_logger(__name__)
    """))

    config_dir = tmp_path / "config" / "settings"
    config_dir.mkdir(parents=True)

    (config_dir / "good.yaml").write_text(textwrap.dedent("""\
        # =============================================================================
        # Good Config
        # =============================================================================
        key: value
    """))

    (config_dir / "bad.yaml").write_text(textwrap.dedent("""\
        key: value
        another: thing
    """))

    excluded_dir = tmp_path / "scripts"
    excluded_dir.mkdir()
    (excluded_dir / "should_skip.py").write_text("import logging\n")

    (tmp_path / ".project_root").touch()
    return tmp_path


class TestOutputSchemas:
    """Tests for Pydantic output schemas."""

    def test_violation_schema_valid(self):
        v = Violation(
            rule_id="no_hardcoded_values",
            file="modules/foo.py",
            line=10,
            message="FOO = 42",
            severity="error",
        )
        assert v.rule_id == "no_hardcoded_values"
        assert v.auto_fixable is False
        assert v.fixed is False

    def test_qa_audit_result_schema_valid(self):
        result = QaAuditResult(
            summary="Found 2 violations",
            total_violations=2,
            error_count=1,
            warning_count=1,
            fixed_count=0,
            needs_human_count=1,
            violations=[
                Violation(
                    rule_id="no_hardcoded_values",
                    file="modules/foo.py",
                    line=10,
                    message="FOO = 42",
                    severity="error",
                ),
            ],
            tests_passed=None,
            scanned_files_count=50,
        )
        assert result.total_violations == 2
        assert len(result.violations) == 1

    def test_violation_with_fix_fields(self):
        v = Violation(
            rule_id="no_datetime_now",
            file="modules/foo.py",
            line=5,
            message="datetime.now()",
            severity="error",
            auto_fixable=True,
            fix_description="Replace with utc_now()",
            fixed=True,
        )
        assert v.auto_fixable is True
        assert v.fixed is True

    def test_violation_with_human_decision(self):
        v = Violation(
            rule_id="no_hardcoded_values",
            file="modules/foo.py",
            line=10,
            message="MAX_LENGTH = 4096",
            severity="error",
            needs_human_decision=True,
            human_question="Is this a platform constant or configurable?",
        )
        assert v.needs_human_decision is True
        assert v.human_question is not None


class TestScannerViaService:
    """Tests for scanner functionality via ComplianceScannerService."""

    def test_finds_relative_import(self, project_with_violations, qa_config):
        scanner = ComplianceScannerService(project_with_violations, qa_config)
        findings = scanner.scan_import_violations()
        relative = [f for f in findings if f["rule_id"] == "no_relative_imports"]
        assert len(relative) >= 1

    def test_finds_direct_logging(self, project_with_violations, qa_config):
        scanner = ComplianceScannerService(project_with_violations, qa_config)
        findings = scanner.scan_import_violations()
        logging_v = [f for f in findings if f["rule_id"] == "no_direct_logging"]
        assert len(logging_v) >= 1

    def test_finds_datetime_violations(self, project_with_violations, qa_config):
        scanner = ComplianceScannerService(project_with_violations, qa_config)
        findings = scanner.scan_datetime_violations()
        assert len(findings) >= 2

    def test_finds_hardcoded_skips_dunders(self, project_with_violations, qa_config):
        scanner = ComplianceScannerService(project_with_violations, qa_config)
        findings = scanner.scan_hardcoded_values()
        names = [f["message"].split(" = ")[0] for f in findings]
        assert "MAX_RETRIES" in names
        assert "__version__" not in names


class TestConfigLoading:
    """Tests for agent config loading from YAML."""

    def test_loads_config_from_yaml(self, qa_config):
        assert qa_config["agent_name"] == "code.qa.agent"
        assert qa_config["enabled"] is True

    def test_config_has_rules(self, qa_config):
        assert len(qa_config["rules"]) > 0

    def test_config_has_exclusions(self, qa_config):
        assert "paths" in qa_config["exclusions"]

    def test_config_has_keywords(self, qa_config):
        assert "compliance" in qa_config["keywords"]

    def test_config_has_model(self, qa_config):
        assert "anthropic:" in qa_config["model"]

    def test_config_has_scope(self, qa_config):
        assert "read" in qa_config.get("scope", {})
        assert "write" in qa_config.get("scope", {})
