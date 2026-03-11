# Building a production-grade security testing agent for Python/FastAPI

The optimal architecture runs **five deterministic scanners in parallel** (Semgrep, Ruff, pip-audit, Gitleaks, Trivy), merges results into unified SARIF, then invokes a PydanticAI triage agent exactly once—only for false-positive filtering, business-logic analysis, and report generation. This "deterministic first, LLM where needed" pattern achieves the best of both worlds: the reproducibility and speed of static tools with the contextual reasoning that only LLMs can provide. Research shows this hybrid approach detects **~61% more real-world vulnerabilities** than pure SAST while reducing false positives by **up to 95%** compared to unfiltered scanner output. The key insight is that PydanticAI has no "tools-only" mode—every tool call requires an LLM decision—so deterministic scanners must run outside the agent loop, with results injected as context for a single LLM triage pass.

---

## The deterministic scanner stack: what to run and why

The recommended combination balances coverage against redundancy. **Semgrep** (v1.154+, `--config auto`) provides deep dataflow and taint analysis with framework-aware rules for FastAPI, SQLAlchemy, and 100+ Python libraries, achieving an **84% true positive rate** on Python code. Its `p/bandit` ruleset reimplements Bandit's checks, making standalone Bandit largely redundant when Semgrep is present. **Ruff** (v0.12+, `--select S`) reimplements Bandit's security rules at extraordinary speed—50,000 lines in 120ms—and slots naturally into any project already using Ruff for linting. Running both Semgrep and Ruff provides complementary coverage: Semgrep handles cross-function dataflow analysis that Ruff cannot, while Ruff catches lint-time security patterns instantly.

For dependency scanning, **pip-audit** (by Trail of Bits, under PyPA) is the clear choice for open-source pipelines. It queries the PyPI Advisory Database and OSV without requiring authentication or payment, outputs JSON and CycloneDX, and supports requirements.txt, pyproject.toml, and PEP 751 lockfiles. Safety CLI 3.x now requires authentication for full database access and charges $25/seat/month for teams, making it less suitable. For broader CVE coverage across both Python dependencies and container images, **Trivy** (v0.69+) aggregates **30+ vulnerability sources** including NVD, GitHub Security Advisories, and distribution-specific feeds—and it can scan dependencies, containers, IaC, and secrets in a single tool.

Secret detection is best handled by **Gitleaks** (v8.30, MIT license) as the primary scanner—it's the fastest option for local directory scanning, supports SARIF output natively, and provides excellent custom regex rules via `.gitleaks.toml`. For high-priority scans, complement with **TruffleHog** (v3.93+), whose verified secret detection actively validates credentials against APIs (700+ detectors), dramatically reducing false positives at the cost of slower execution. Research shows the two tools find **non-overlapping sets of true positives**, making them genuinely complementary.

For Docker and container security, the pipeline splits into pre-build and post-build phases. **Hadolint** (v2.12) remains the de facto Dockerfile linter, enforcing best practices like avoiding `:latest` tags, using `--no-install-recommends`, setting non-root USER, and enabling `pipefail`. **Checkov** (v3.x) extends this to Docker Compose files, catching privileged containers, exposed ports, sensitive volume mounts, `network_mode: host`, and missing resource limits. Post-build, **Trivy** scans the built image for CVEs, secrets in layers, and misconfigurations, while **Dockle** (v0.4.13) validates against the CIS Docker Benchmark—checking for setuid/setgid permissions, empty passwords, and sudo usage that static Dockerfile analysis cannot detect.

### SARIF as the universal interchange format

Tool SARIF support varies significantly. Semgrep, Bandit (via `bandit[sarif]`), Gitleaks, Trivy, Grype, Checkov, and KICS all produce **native SARIF 2.1.0 output**. Hadolint and Dockle do not, requiring conversion from their JSON output. For tools lacking SARIF support, the simplest approach is a Python converter that maps JSON findings into the SARIF schema—SARIF is just JSON with a well-defined structure. The Microsoft `sarif-multitool` (`npm i -g @microsoft/sarif-multitool`) provides a `merge` command for combining multiple SARIF files, while the Python `sarif-tools` package offers diff, copy, and summary operations. For maximum control, direct JSON manipulation in Python is most reliable:

```python
def merge_sarif_files(paths: list[str]) -> dict:
    merged = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": []
    }
    for path in paths:
        with open(path) as f:
            merged["runs"].extend(json.load(f).get("runs", []))
    return merged
```

The critical SARIF fields for downstream processing are `ruleId` (links to rule metadata), `level` (error/warning/note), `locations[].physicalLocation` (file, line, snippet), `partialFingerprints` (for deduplication across runs), and `properties.security-severity` (numeric 0–10 score used by GitHub Code Scanning). The `fixes[]` array can represent proposed code changes with `deletedRegion` and `insertedContent`, though most tools do not populate this field today.

---

## Where deterministic tools fail and LLMs must step in

The EASE 2024 benchmark tested four SAST tools against 170 manually curated commits with known vulnerabilities. **All four tools combined detected only 38.8% of real-world vulnerabilities.** DryRun Security's independent testing confirmed that no SAST tool reliably catches IDOR, broken access control, or authentication logic flaws. The root cause, as Gecko Security's analysis explains, is that ASTs are "semantically empty"—they capture syntax but not relationships between components. Business logic vulnerabilities aren't data-flow questions; they're questions about correctness. A Cal.com authentication bypass existed across three files where each file looked reasonable in isolation; an AST-based scanner examining any file individually would see syntactically valid code.

**False-positive filtering is the most mature LLM application** in security. The SAST-Genius framework (arXiv 2509.15433) fine-tuned Llama 3 8B on vetted false-positive/true-positive datasets and achieved **89.5% precision** versus Semgrep's 35.7% baseline—reducing false positives from 225 to 20, an 11× improvement. The "Sifting the Noise" study (arXiv 2601.22952) reduced the OWASP Benchmark false-positive rate from **>92% to 6.3%** using agentic frameworks. Commercially, Semgrep Assistant achieves **96% alignment with human triage decisions**, and Endor Labs claims **up to 95% false-positive reduction** through multi-agent orchestration. The residual false positives concentrate in policy-related and cryptographic CWEs, while injection-style vulnerabilities are filtered reliably.

Context-dependent triage is particularly valuable for ORM-heavy codebases. Bandit's B608 rule flags any string concatenation resembling SQL, regardless of whether SQLAlchemy's parameterized query builders are used—generating false positives that cause alert blindness. An LLM can distinguish between `session.query(User).filter(User.username == name)` (safe—ORM parameterizes automatically) and `session.execute(text(f"SELECT * FROM {table}"))` (dangerous—f-string bypasses parameterization). The SAST-Genius approach prompts the LLM with the specific question "Does this user input lead to an exploitable SQL injection?" alongside code context and data-flow paths, achieving the precision gains noted above.

Attack path analysis—connecting multiple low-severity findings into meaningful attack narratives—is an emerging LLM capability. Kodem Security's approach uses three steps: context enrichment with runtime and static information, LLM-generated attack scenarios enumerating attacker steps, and LLM-as-judge validation filtering illogical scenarios. The Aurora framework (arXiv 2407.16928) generated **300+ distinct attack chains** within seconds using LLMs to extract features from MITRE ATT&CK and link them into kill graphs.

The areas where even LLMs struggle deserve honest acknowledgment. **Timing side channels and race conditions remain largely unsolved**—the arXiv 2602.16741 study found these are "consistently missed" patterns even by strong LLMs, because the vulnerability exists in *how long* execution takes rather than *what* the code computes. Java cryptography vulnerabilities achieved only **50% detection** under best LLM conditions. These gaps mean the agent should flag but not promise reliable detection for these vulnerability classes.

---

## The scan-triage-analyze-report pipeline architecture

The most effective architecture follows a four-phase pipeline, modeled after SAST-Genius and IRIS but adapted for the PydanticAI runtime. The first phase runs all deterministic scanners in parallel using `asyncio.create_subprocess_exec`, collecting SARIF/JSON outputs. The second phase merges and deduplicates findings—using `file_path + line_number + CWE_ID` as the primary dedup key, with code snippet hashing as a secondary key. The third phase invokes the LLM exactly once for triage, false-positive assessment, and contextual analysis. The fourth phase generates structured output and natural-language reporting.

This matches how the most successful commercial and research systems work. **GitHub Copilot Autofix** runs CodeQL deterministically, produces SARIF alerts, then feeds alert data, code snippets around source/sink locations, and query help text into GPT-4o—achieving **3× faster remediation** (28 minutes versus 1.5 hours) and **12× faster for SQL injection** specifically. The IRIS system (arXiv 2405.17238) uses a neuro-symbolic approach: static analysis extracts candidate APIs, LLMs label them as sources/sinks, CodeQL runs taint analysis, then LLMs triage the resulting alerts—detecting **55 vulnerabilities versus CodeQL's 27** while reducing false positives by **80%**.

For LLM-generated custom rules, **Autogrep** (github.com/lambdasec/autogrep) demonstrates that vulnerability patches can be automatically transformed into Semgrep rules—processing 39,931 patches into **645 high-quality rules** across 20 languages. The RuleLLM system achieves **85.2% precision and 91.8% recall** generating Semgrep and YARA rules from malware samples. These approaches enable the agent to learn codebase-specific patterns over time.

The most effective prompt pattern for security triage combines SAST cross-referencing with chain-of-thought reasoning. The arXiv 2602.16741 study found that injecting static analysis findings as verification hints into LLM prompts achieved a **96.9% detection rate** with **47% recovery of baseline misses**—outperforming every other prompting strategy tested, including comment stripping, skeptical prompts, and structured methodology. The prompt should include: the SARIF finding (rule ID, severity, CWE), the affected code snippet with ±5 lines of context, the enclosing function/class, and any intermediate dataflow steps with file names and line numbers.

---

## Orchestrating parallel scanners with deduplication and severity normalization

The deterministic phase runs all scanners concurrently via asyncio with per-scanner timeout handling and partial-failure tolerance. Each scanner's exit code semantics differ—Semgrep returns 1 for findings found (not failure), Bandit returns 1 for issues found, pip-audit returns 1 for vulnerabilities, and Trivy returns 0 by default regardless of findings unless `--exit-code` is set. The orchestrator must treat "findings found" exit codes as success:

```python
async def run_scanner(cmd: list[str], name: str, timeout: int = 300) -> ScannerResult:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return ScannerResult(name=name, status="completed", exit_code=proc.returncode,
                           output=stdout.decode())
    except asyncio.TimeoutError:
        return ScannerResult(name=name, status="timeout", exit_code=-1, output="")
    except Exception as e:
        return ScannerResult(name=name, status="error", exit_code=-1, output=str(e))
```

**Severity normalization** maps each tool's native scale to a unified `security-severity` score (0–10), following the pattern GitHub Code Scanning uses. Bandit HIGH maps to 7.5, Semgrep ERROR to 8.0, Trivy CRITICAL to 9.5, and all Gitleaks secret findings to 8.5. Dependency vulnerabilities use their actual CVSS v3 score when available. This numeric scale feeds into both SARIF's `properties.security-severity` field and the agent's prioritization logic.

Finding deduplication follows DefectDojo's proven approach: SHA-256 hash of `cwe + severity + file_path + line_number`, with tool-specific context preserved in a `relatedTools` property. When Semgrep and Ruff both flag the same line for the same CWE, the merged finding retains both rule IDs and descriptions while appearing as a single entry. For incremental scanning, Semgrep's `--baseline-ref` flag enables diff-aware scanning of only changed files, and Bandit can be fed file lists from `git diff --name-only`. A file-hash cache avoids re-scanning unchanged files across runs entirely.

---

## Structuring the agent in PydanticAI

The critical architectural decision is separating deterministic execution from LLM reasoning. **PydanticAI requires an LLM decision for every tool call**—there is no "tools-only" execution mode. Therefore, the deterministic scanners run outside the agent loop via plain asyncio, and results are injected into the agent as context for a single triage pass. This is the "programmatic hand-off" pattern from PydanticAI's multi-agent documentation:

```python
async def security_scan(target: str, scan_id: str) -> ScanResult:
    # PHASE 1: Deterministic — no LLM tokens consumed
    file_types = detect_file_types(target)
    raw_results = await run_all_scanners(target, file_types)
    merged_sarif = merge_and_dedup(raw_results)
    
    # PHASE 2: LLM triage — invoked exactly once
    triage_agent = Agent(
        'anthropic:claude-sonnet-4-20250514',
        output_type=ScanResult,
        instructions=TRIAGE_INSTRUCTIONS,
    )
    result = await triage_agent.run(
        f'Triage these findings for {target}:\n\n{json.dumps(merged_sarif)}',
        usage_limits=UsageLimits(request_limit=5),
    )
    return result.output
```

The `ScanResult` output model leverages Pydantic's validation to guarantee the LLM returns properly typed, structured data. PydanticAI converts the model to a JSON Schema, registers it as an "output tool" with the LLM, and validates the response—retrying on validation failure. The model hierarchy includes `ScanResult` (top-level with executive summary, risk score, scanner metadata) containing a list of `Finding` objects (each with tool source, rule ID, severity enum, CWE ID, file location, description, false-positive assessment, and remediation guidance).

For scans where the agent needs to make decisions about *which* scanners to run—for instance, when receiving a mixed repository with both Python and Docker artifacts—the `prepare_tools` mechanism dynamically filters the tool set based on detected file types:

```python
async def select_tools_by_target(
    ctx: RunContext[ScanDependencies], tool_defs: list[ToolDefinition]
) -> list[ToolDefinition]:
    python_tools = {'run_semgrep', 'run_bandit', 'run_pip_audit'}
    docker_tools = {'run_trivy_image', 'run_hadolint', 'run_checkov'}
    allowed = {'run_gitleaks'}  # always available
    if any(f.endswith('.py') for f in ctx.deps.file_types):
        allowed |= python_tools
    if 'Dockerfile' in ctx.deps.file_types:
        allowed |= docker_tools
    return [td for td in tool_defs if td.name in allowed]
```

Integration with the BFA stack uses Taskiq for background task scheduling and structlog (via Pydantic Logfire's OpenTelemetry bridge) for observability. The FastAPI endpoint accepts a scan request, enqueues a Taskiq task, and the worker runs the full deterministic-then-LLM pipeline asynchronously. `UsageLimits(request_limit=20, tool_calls_limit=15)` caps LLM API costs per scan.

---

## Docker security analysis beyond basic linting

The Docker security pipeline addresses four distinct concerns that require different tools. **Dockerfile best-practice enforcement** is Hadolint's domain—it catches `:latest` tags (DL3006/DL3007), missing `--no-install-recommends` (DL3015), root USER (DL3002), ADD instead of COPY (DL3009), and missing SHELL pipefail (DL4006). Checkov extends this to Docker Compose, detecting privileged containers, sensitive volume mounts (`/`, `/etc`, `/proc`), `network_mode: host`, missing memory/CPU limits, and exposed port 22.

**Post-build image analysis** catches issues invisible to Dockerfile linting. Trivy's `trivy image --scanners vuln,secret` scans all layers for CVEs and leaked secrets—including secrets that exist only in intermediate build layers of multi-stage builds. Grype's `--scope all-layers` flag provides complementary CVE coverage from different vulnerability databases. Dockle's CIS Docker Benchmark checks add setuid/setgid permission detection (CIS-DI-0008) and empty password detection (DKL-LI-0001) that no other tool covers.

For the LLM layer, Docker security analysis benefits from reasoning about multi-stage build patterns that linting cannot express. An LLM can assess whether a `COPY --from=builder` stage properly excludes `.env` files, whether the final stage's package installation is minimal, and whether the base image choice (e.g., `python:3.12-slim` versus `python:3.12` versus a distroless image) appropriately balances functionality against attack surface. Base image freshness can be assessed by running `trivy image` against the base image tag and comparing CVE counts against alternatives.

---

## Conclusion: the implementation path forward

The architecture that emerges from this research is clear in its separation of concerns. Deterministic tools handle **100% of pattern-matching** work—SAST, dependency CVEs, secret detection, Dockerfile linting, IaC misconfiguration—with SARIF as the universal interchange format. The LLM is reserved for exactly five tasks that deterministic tools genuinely cannot perform: false-positive triage (with demonstrated 11× improvement), business-logic vulnerability detection (which SAST misses entirely), context-dependent assessment of ORM/framework usage patterns, attack-path chaining across multiple low-severity findings, and natural-language report generation. The recommended tool stack—Semgrep + Ruff + pip-audit + Gitleaks + Trivy + Hadolint + Checkov—covers Python SAST, dependency scanning, secret detection, container CVEs, Dockerfile linting, and IaC misconfiguration using exclusively open-source tools with native or easily-converted SARIF output. The PydanticAI integration uses the programmatic hand-off pattern to ensure the LLM is invoked exactly once per scan, keeping costs predictable and latency bounded while still delivering the contextual reasoning that transforms raw scanner noise into actionable security intelligence.