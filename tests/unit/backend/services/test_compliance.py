"""
Unit Tests for ComplianceScannerService.

Tests use real temporary files — no mocks.
"""

import textwrap

import pytest

from modules.backend.services.compliance import ComplianceScannerService, load_config


@pytest.fixture
def qa_config():
    """Load the real QA agent config from disk."""
    return load_config()


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


class TestComplianceScannerService:
    """Tests for ComplianceScannerService using real temp files."""

    def _scanner(self, project_root, qa_config):
        return ComplianceScannerService(project_root, qa_config)

    def test_collect_python_files(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        files = scanner.collect_python_files()
        py_files = [f for f in files if f.endswith(".py")]
        assert len(py_files) > 0

    def test_collect_respects_exclusions(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        files = scanner.collect_python_files()
        assert not any(f.startswith("scripts/") for f in files)

    def test_scan_imports_finds_relative(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_import_violations()
        relative = [f for f in findings if f["rule_id"] == "no_relative_imports"]
        assert len(relative) >= 1

    def test_scan_imports_finds_direct_logging(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_import_violations()
        logging_violations = [f for f in findings if f["rule_id"] == "no_direct_logging"]
        assert len(logging_violations) >= 1

    def test_scan_imports_finds_os_getenv_fallback(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_import_violations()
        getenv = [f for f in findings if f["rule_id"] == "no_os_getenv_fallback"]
        assert len(getenv) >= 1

    def test_scan_datetime_violations(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_datetime_violations()
        assert len(findings) >= 2

    def test_scan_hardcoded_finds_constants(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_hardcoded_values()
        names = [f["message"].split(" = ")[0] for f in findings]
        assert "MAX_RETRIES" in names
        assert "TIMEOUT_SECONDS" in names
        assert "API_VERSION" in names

    def test_scan_hardcoded_skips_dunders(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_hardcoded_values()
        names = [f["message"].split(" = ")[0] for f in findings]
        assert "__version__" not in names
        assert "__all__" not in names

    def test_scan_file_sizes_flags_large(self, tmp_path, qa_config):
        large_file = tmp_path / "big.py"
        large_file.write_text("\n".join(f"line_{i} = {i}" for i in range(1100)))
        (tmp_path / ".project_root").touch()

        scanner = self._scanner(tmp_path, qa_config)
        findings = scanner.scan_file_sizes()
        assert any("big.py" in f["file"] for f in findings)

    def test_scan_config_files_good_yaml(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_config_files()
        good_findings = [f for f in findings if "good.yaml" in f["file"]]
        assert len(good_findings) == 0

    def test_scan_config_files_bad_yaml(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_config_files()
        bad_findings = [f for f in findings if "bad.yaml" in f["file"]]
        assert len(bad_findings) >= 1

    def test_scan_all_returns_combined(self, project_with_violations, qa_config):
        scanner = self._scanner(project_with_violations, qa_config)
        findings = scanner.scan_all()
        rule_ids = {f["rule_id"] for f in findings}
        assert "no_relative_imports" in rule_ids
        assert "no_datetime_now" in rule_ids


class TestConfigLoading:
    """Tests for agent config loading from YAML."""

    def test_loads_config_from_yaml(self, qa_config):
        assert qa_config["agent_name"] == "code.qa.agent"
        assert qa_config["enabled"] is True

    def test_config_has_rules(self, qa_config):
        assert len(qa_config["rules"]) > 0

    def test_config_has_exclusions(self, qa_config):
        assert "paths" in qa_config["exclusions"]

    def test_config_has_scope(self, qa_config):
        assert "read" in qa_config.get("scope", {})
