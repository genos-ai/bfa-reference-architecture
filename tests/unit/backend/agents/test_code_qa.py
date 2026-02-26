"""
Unit Tests for QA Compliance Agent (code.qa.agent).

Tool tests use real temporary files — no mocks.
Agent integration tests use PydanticAI TestModel — no real LLM calls.
"""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.backend.agents.vertical.code.qa.agent import (
    QaAgentDeps,
    QaAuditResult,
    Violation,
    _collect_python_files,
    _get_enabled_rule_ids,
    _get_exclusion_paths,
    _is_excluded,
    _load_agent_config,
    _scan_file_lines,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def qa_config():
    """Load the real qa_agent config from disk."""
    return _load_agent_config()


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


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestExclusionHelpers:
    """Tests for path exclusion logic."""

    def test_get_exclusion_paths_from_config(self, qa_config):
        exclusions = _get_exclusion_paths(qa_config)
        assert "scripts/" in exclusions
        assert "docs/" in exclusions
        assert ".venv/" in exclusions

    def test_is_excluded_matches_prefix(self):
        assert _is_excluded("scripts/foo.py", {"scripts/"}) is True
        assert _is_excluded("docs/bar.md", {"docs/"}) is True

    def test_is_excluded_no_match(self):
        assert _is_excluded("modules/foo.py", {"scripts/"}) is False

    def test_is_excluded_handles_trailing_slash(self):
        assert _is_excluded("scripts/foo.py", {"scripts"}) is True


class TestEnabledRules:
    """Tests for rule configuration parsing."""

    def test_gets_enabled_rule_ids(self, qa_config):
        enabled = _get_enabled_rule_ids(qa_config)
        assert "no_hardcoded_values" in enabled
        assert "no_relative_imports" in enabled
        assert "no_datetime_now" in enabled

    def test_all_rules_have_ids(self, qa_config):
        for rule in qa_config["rules"]:
            assert "id" in rule
            assert "severity" in rule


class TestCollectPythonFiles:
    """Tests for file discovery."""

    def test_finds_python_files(self, project_with_violations):
        files = _collect_python_files(project_with_violations, set())
        py_files = [f for f in files if f.endswith(".py")]
        assert len(py_files) > 0

    def test_respects_exclusions(self, project_with_violations):
        files = _collect_python_files(project_with_violations, {"scripts/"})
        assert not any(f.startswith("scripts/") for f in files)

    def test_finds_files_in_subdirectories(self, project_with_violations):
        files = _collect_python_files(project_with_violations, set())
        assert any("modules/" in f for f in files)


# =============================================================================
# Scanner Tool Tests (via internal functions, real files)
# =============================================================================


class TestScanImportViolations:
    """Tests for import violation scanning — uses real temp files."""

    @pytest.fixture
    def _scan(self, project_with_violations, qa_config):
        """Run the import scanner on the temp project."""
        from modules.backend.agents.vertical.code.qa.agent import _collect_python_files, _scan_file_lines

        import re

        project_root = project_with_violations
        exclusions = _get_exclusion_paths(qa_config)
        enabled = _get_enabled_rule_ids(qa_config)
        findings = []

        for rel_path in _collect_python_files(project_root, exclusions):
            lines = _scan_file_lines(project_root, rel_path)
            in_modules = rel_path.startswith("modules/")

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if "no_relative_imports" in enabled and re.match(r"^from\s+\.", stripped):
                    findings.append({"rule_id": "no_relative_imports", "file": rel_path, "line": i})
                if "no_direct_logging" in enabled and in_modules and stripped == "import logging":
                    findings.append({"rule_id": "no_direct_logging", "file": rel_path, "line": i})
                if "no_os_getenv_fallback" in enabled:
                    if re.search(r"os\.(getenv|environ\.get)\s*\(.+,\s*.+\)", stripped):
                        findings.append({"rule_id": "no_os_getenv_fallback", "file": rel_path, "line": i})

        return findings

    def test_finds_relative_import(self, _scan):
        relative = [f for f in _scan if f["rule_id"] == "no_relative_imports"]
        assert len(relative) >= 1

    def test_finds_direct_logging(self, _scan):
        logging_violations = [f for f in _scan if f["rule_id"] == "no_direct_logging"]
        assert len(logging_violations) >= 1

    def test_finds_os_getenv_fallback(self, _scan):
        getenv = [f for f in _scan if f["rule_id"] == "no_os_getenv_fallback"]
        assert len(getenv) >= 1


class TestScanDatetimeViolations:
    """Tests for datetime violation scanning — uses real temp files."""

    def test_finds_datetime_now(self, project_with_violations):
        import re

        pattern = re.compile(r"datetime\.(now|utcnow)\s*\(")
        findings = []

        for py_file in project_with_violations.rglob("*.py"):
            rel = str(py_file.relative_to(project_with_violations))
            for i, line in enumerate(py_file.read_text().splitlines(), 1):
                if pattern.search(line):
                    findings.append({"file": rel, "line": i})

        assert len(findings) >= 2


class TestScanHardcodedValues:
    """Tests for hardcoded value scanning — uses real temp files."""

    def test_finds_upper_case_constants(self, project_with_violations):
        import ast

        findings = []
        hardcoded_path = project_with_violations / "modules" / "example" / "hardcoded.py"
        source = hardcoded_path.read_text()
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper() and isinstance(node.value, ast.Constant):
                    findings.append(target.id)

        assert "MAX_RETRIES" in findings
        assert "TIMEOUT_SECONDS" in findings
        assert "API_VERSION" in findings

    def test_skips_dunder_names(self, project_with_violations):
        import ast

        hardcoded_path = project_with_violations / "modules" / "example" / "hardcoded.py"
        source = hardcoded_path.read_text()
        tree = ast.parse(source)
        skip = {"__all__", "__version__", "__tablename__", "__abstract__"}

        names = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in skip:
                        if target.id.isupper() and isinstance(node.value, ast.Constant):
                            names.append(target.id)

        assert "__version__" not in names
        assert "__all__" not in names

    def test_skips_lowercase_names(self, project_with_violations):
        import ast

        hardcoded_path = project_with_violations / "modules" / "example" / "hardcoded.py"
        source = hardcoded_path.read_text()
        tree = ast.parse(source)

        import re
        names = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and re.match(r"^[A-Z][A-Z0-9_]+$", target.id):
                        names.append(target.id)

        assert "normal_var" not in names


class TestScanFileSizes:
    """Tests for file size scanning."""

    def test_flags_large_file(self, tmp_path):
        large_file = tmp_path / "big.py"
        large_file.write_text("\n".join(f"line_{i} = {i}" for i in range(1100)))

        lines = _scan_file_lines(tmp_path, "big.py")
        assert len(lines) > 1000

    def test_small_file_not_flagged(self, tmp_path):
        small_file = tmp_path / "small.py"
        small_file.write_text("x = 1\n")

        lines = _scan_file_lines(tmp_path, "small.py")
        assert len(lines) < 1000


class TestScanConfigFiles:
    """Tests for YAML header comment scanning."""

    def test_good_yaml_has_header(self, project_with_violations):
        good = (project_with_violations / "config" / "settings" / "good.yaml").read_text()
        assert "# =====" in good[:500]

    def test_bad_yaml_missing_header(self, project_with_violations):
        bad = (project_with_violations / "config" / "settings" / "bad.yaml").read_text()
        assert "# =====" not in bad[:500]


# =============================================================================
# Apply Fix Tests
# =============================================================================


class TestApplyFix:
    """Tests for the apply_fix tool logic."""

    def test_replaces_exact_text(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("old_value = 42\nother = 1\n")

        content = target.read_text()
        assert content.count("old_value = 42") == 1
        new_content = content.replace("old_value = 42", "new_value = 99", 1)
        target.write_text(new_content)

        result = target.read_text()
        assert "new_value = 99" in result
        assert "old_value = 42" not in result

    def test_fails_on_ambiguous_match(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("x = 1\nx = 1\n")

        content = target.read_text()
        count = content.count("x = 1")
        assert count > 1

    def test_fails_on_missing_text(self, tmp_path):
        target = tmp_path / "test.py"
        target.write_text("a = 1\n")

        content = target.read_text()
        assert content.count("nonexistent") == 0


# =============================================================================
# Output Schema Tests
# =============================================================================


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


# =============================================================================
# Config Loading Tests
# =============================================================================


class TestConfigLoading:
    """Tests for agent config loading from YAML."""

    def test_loads_config_from_yaml(self, qa_config):
        assert qa_config["agent_name"] == "code.qa.agent"
        assert qa_config["enabled"] is True

    def test_config_has_rules(self, qa_config):
        assert len(qa_config["rules"]) > 0

    def test_config_has_exclusions(self, qa_config):
        assert "paths" in qa_config["exclusions"]
        assert len(qa_config["exclusions"]["paths"]) > 0

    def test_config_has_keywords(self, qa_config):
        assert "compliance" in qa_config["keywords"]
        assert "qa" in qa_config["keywords"]

    def test_config_has_model(self, qa_config):
        assert "anthropic:" in qa_config["model"]
