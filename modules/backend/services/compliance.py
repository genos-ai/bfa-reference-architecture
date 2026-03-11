"""
Compliance Scanner Service.

Deterministic rule-based scanner that audits Python codebases for
compliance violations. Business logic for the code.quality.agent and
the scripts/compliance_checker.py CLI. No LLM dependency.

Usage:
    from modules.backend.services.compliance import ComplianceScannerService

    scanner = ComplianceScannerService(project_root, config)
    violations = scanner.scan_import_violations()
"""

import ast
import re
from pathlib import Path
from typing import Any

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class ComplianceScannerService:
    """Scans a Python codebase for compliance rule violations.

    Each scan method is deterministic (no LLM). Methods accept no external
    state beyond what was provided at construction. Results are returned
    as lists of finding dicts suitable for both agent tools and CLI output.
    """

    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self._project_root = project_root
        self._config = config
        self._exclusion_paths = self._get_exclusion_paths()
        self._enabled_rules = self._get_enabled_rule_ids()

    # =========================================================================
    # Config helpers
    # =========================================================================

    def _get_exclusion_paths(self) -> set[str]:
        return set(self._config.get("exclusions", {}).get("paths", []))

    def _get_enabled_rule_ids(self) -> set[str]:
        return {
            rule["id"]
            for rule in self._config.get("rules", [])
            if rule.get("enabled", True)
        }

    def get_rule_severity(self, rule_id: str) -> str:
        """Get severity for a rule from config."""
        for rule in self._config.get("rules", []):
            if rule["id"] == rule_id:
                return rule.get("severity", "warning")
        return "warning"

    # =========================================================================
    # File helpers
    # =========================================================================

    def collect_python_files(self) -> list[str]:
        """Walk the project and collect .py files, respecting exclusions."""
        files: list[str] = []
        for py_file in sorted(self._project_root.rglob("*.py")):
            rel = str(py_file.relative_to(self._project_root))
            if not self._is_excluded(rel):
                files.append(rel)
        return files

    def scan_file_lines(self, rel_path: str) -> list[str]:
        """Read a file and return its lines."""
        full_path = self._project_root / rel_path
        if not full_path.is_file():
            return []
        return full_path.read_text(encoding="utf-8").splitlines()

    def _is_excluded(self, file_path: str) -> bool:
        for excl in self._exclusion_paths:
            if file_path.startswith(excl) or file_path.startswith(excl.rstrip("/")):
                return True
        return False

    # =========================================================================
    # Scanners
    # =========================================================================

    def scan_import_violations(self) -> list[dict]:
        """Scan for relative imports, direct ``import logging``, and
        ``os.getenv()`` with hardcoded fallback defaults."""
        findings: list[dict] = []

        for rel_path in self.collect_python_files():
            lines = self.scan_file_lines(rel_path)
            in_modules = rel_path.startswith("modules/")
            is_core_logging = rel_path == "modules/backend/core/logging.py"

            for i, line in enumerate(lines, 1):
                stripped = line.strip()

                if "no_relative_imports" in self._enabled_rules and re.match(
                    r"^from\s+\.", stripped
                ):
                    findings.append({
                        "rule_id": "no_relative_imports",
                        "file": rel_path,
                        "line": i,
                        "message": stripped,
                    })

                if (
                    "no_direct_logging" in self._enabled_rules
                    and in_modules
                    and not is_core_logging
                    and stripped == "import logging"
                ):
                    findings.append({
                        "rule_id": "no_direct_logging",
                        "file": rel_path,
                        "line": i,
                        "message": "Direct 'import logging' — use get_logger() from core.logging",
                    })

                if "no_os_getenv_fallback" in self._enabled_rules:
                    if re.search(
                        r"os\.(getenv|environ\.get)\s*\(.+,\s*.+\)", stripped
                    ):
                        findings.append({
                            "rule_id": "no_os_getenv_fallback",
                            "file": rel_path,
                            "line": i,
                            "message": stripped,
                        })

        return findings

    def scan_datetime_violations(self) -> list[dict]:
        """Scan for ``datetime.now()`` and ``datetime.utcnow()`` usage."""
        findings: list[dict] = []

        if "no_datetime_now" not in self._enabled_rules:
            return findings

        skip_files = {"modules/backend/core/utils.py"}
        pattern = re.compile(r"datetime\.(now|utcnow)\s*\(")

        for rel_path in self.collect_python_files():
            if rel_path in skip_files:
                continue
            lines = self.scan_file_lines(rel_path)
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    findings.append({
                        "rule_id": "no_datetime_now",
                        "file": rel_path,
                        "line": i,
                        "message": line.strip(),
                    })

        return findings

    def scan_hardcoded_values(self) -> list[dict]:
        """Scan for module-level UPPER_CASE constants with literal values
        that likely should be in YAML config."""
        findings: list[dict] = []

        if "no_hardcoded_values" not in self._enabled_rules:
            return findings

        skip_names = {
            "__all__", "__version__", "__tablename__", "__abstract__",
            "VALID_SOURCES", "EXCEPTION_STATUS_MAP", "EVENT_TYPE_MAP",
            "MODEL_COST_PER_MILLION_TOKENS", "DEFAULT_COST_PER_MILLION",
            "SYSTEM_PROMPT",
        }
        skip_names.update(self._config.get("hardcoded_skip_names", []))

        for rel_path in self.collect_python_files():
            full_path = self._project_root / rel_path
            try:
                source = full_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.iter_child_nodes(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    name = target.id
                    if name in skip_names:
                        continue
                    if not re.match(r"^[A-Z][A-Z0-9_]+$", name):
                        continue
                    if not isinstance(node.value, ast.Constant):
                        continue
                    val = node.value.value
                    if isinstance(val, (int, float, str)) and not isinstance(val, bool):
                        findings.append({
                            "rule_id": "no_hardcoded_values",
                            "file": rel_path,
                            "line": node.lineno,
                            "message": f"{name} = {val!r}",
                        })

        return findings

    def scan_file_sizes(self) -> list[dict]:
        """Scan for Python files exceeding the configured line limit."""
        findings: list[dict] = []

        if "file_size_limit" not in self._enabled_rules:
            return findings

        limit = self._config.get("file_size_limit", 1000)

        for rel_path in self.collect_python_files():
            lines = self.scan_file_lines(rel_path)
            count = len(lines)
            if count > limit:
                findings.append({
                    "rule_id": "file_size_limit",
                    "file": rel_path,
                    "line": None,
                    "message": f"{count} lines (limit: {limit})",
                })

        return findings

    def scan_cli_options(self) -> list[dict]:
        """Scan root-level CLI scripts for positional arguments
        and missing --verbose/--debug flags."""
        findings: list[dict] = []

        root_py_files = sorted(self._project_root.glob("*.py"))

        for full_path in root_py_files:
            rel_path = str(full_path.relative_to(self._project_root))
            try:
                source = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if "cli_options_not_positional" in self._enabled_rules:
                if "add_argument" in source:
                    try:
                        tree = ast.parse(source)
                        for node in ast.walk(tree):
                            if (
                                isinstance(node, ast.Call)
                                and isinstance(node.func, ast.Attribute)
                                and node.func.attr == "add_argument"
                                and node.args
                            ):
                                first_arg = node.args[0]
                                if (
                                    isinstance(first_arg, ast.Constant)
                                    and isinstance(first_arg.value, str)
                                    and not first_arg.value.startswith("-")
                                ):
                                    findings.append({
                                        "rule_id": "cli_options_not_positional",
                                        "file": rel_path,
                                        "line": node.lineno,
                                        "message": f"Positional argument: {first_arg.value!r}",
                                    })
                    except SyntaxError:
                        pass

            if "cli_verbose_debug" in self._enabled_rules:
                has_verbose = "--verbose" in source
                has_debug = "--debug" in source
                if not has_verbose or not has_debug:
                    missing = []
                    if not has_verbose:
                        missing.append("--verbose")
                    if not has_debug:
                        missing.append("--debug")
                    findings.append({
                        "rule_id": "cli_verbose_debug",
                        "file": rel_path,
                        "line": None,
                        "message": f"Missing CLI options: {', '.join(missing)}",
                    })

        return findings

    def scan_config_files(self) -> list[dict]:
        """Scan YAML config files for missing option header comments."""
        findings: list[dict] = []

        if "yaml_header_comment" not in self._enabled_rules:
            return findings

        yaml_dirs = [
            self._project_root / "config" / "settings",
            self._project_root / "config" / "agents",
        ]

        for yaml_dir in yaml_dirs:
            if not yaml_dir.exists():
                continue
            for yaml_path in sorted(yaml_dir.rglob("*.yaml")):
                rel_path = str(yaml_path.relative_to(self._project_root))
                try:
                    head = yaml_path.read_text(encoding="utf-8")[:500]
                except (OSError, UnicodeDecodeError):
                    continue

                if "# =====" not in head:
                    findings.append({
                        "rule_id": "yaml_header_comment",
                        "file": rel_path,
                        "line": 1,
                        "message": "YAML file missing commented option header",
                    })

        return findings

    def scan_all(self) -> list[dict]:
        """Run all enabled scanners and return a flat list of findings."""
        findings: list[dict] = []
        findings.extend(self.scan_import_violations())
        findings.extend(self.scan_datetime_violations())
        findings.extend(self.scan_hardcoded_values())
        findings.extend(self.scan_file_sizes())
        findings.extend(self.scan_cli_options())
        findings.extend(self.scan_config_files())
        return findings
