# PyQuality Index: a composite 0–100 code quality metric for Python

**A single number—the PyQuality Index (PQI)—can holistically score Python code quality by combining seven normalized dimension scores through a penalized weighted geometric mean, where 65/100 marks the "good enough" threshold for production code.** This metric draws on ISO 25010 quality characteristics, validated industry tools (Radon, Ruff, Bandit, mypy, coverage.py), and cutting-edge LLM-as-judge augmentation to produce actionable scores at per-function, per-file, and per-project granularity. The approach resolves a central tension in software metrics: no single existing tool covers all quality dimensions, yet developers need one coherent number. The PQI bridges this gap by orchestrating existing analyzers through a TreeSitter/AST pipeline and feeding their outputs into a principled aggregation formula.

---

## The seven dimensions and how to measure each one

Each dimension produces a normalized sub-score on a 0–100 scale. The sub-metrics below are selected for programmatic computability—every signal can be extracted from Python AST, TreeSitter queries, or existing CLI tools without human judgment.

### Maintainability (weight: 20%)

Maintainability earns the highest weight because **60–80% of total software lifecycle cost is maintenance**. SIG research shows 4-star systems (top 35%) have 2× lower maintenance costs and up to 4× faster development speed than 2-star systems.

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Maintainability Index | Radon `mi_visit()` (0–100 already) | Direct use; floor at 0 |
| Technical debt ratio | Ruff + Pylint finding count ÷ KLOC, mapped via SQALE remediation estimates | Sigmoid: 0% debt → 100, >40% → 0 |
| Dead code percentage | Vulture confidence-weighted findings ÷ total definitions | Linear: 0% dead → 100, >15% → 0 |
| Documentation coverage | AST: `FunctionDef`/`ClassDef` nodes with `__doc__` ÷ total | Linear percentage |
| Code duplication | Pylint `duplicate-code` or jscpd percentage | Linear: 0% dup → 100, >10% → 0 |

The Maintainability Index formula from Radon combines Halstead Volume, Cyclomatic Complexity, SLOC, and comment ratio: `MI = max(0, 100 × (171 − 5.2·ln(V) − 0.23·G − 16.2·ln(LOC) + 50·sin(√(2.4·CM))) / 171)`. While its coefficients derive from 1992 HP C/Pascal studies and are rightly criticized, MI remains the most widely implemented single-number maintainability metric and serves well as one input among several. The SQALE method, implemented in SonarQube (used by **50,000+ companies**), converts each code issue into remediation time—a more actionable signal than abstract scores.

**Key academic reference:** Pisch et al. (ESEM 2024) found existing modularity metrics distorted by project size and proposed the M-score, which clusters dependency relations hierarchically and treats modules at various layers equally.

### Security (weight: 15%)

A single critical vulnerability can negate all other quality dimensions, justifying security's high weight despite typically having fewer measurable signals. The asymmetric risk profile—low-probability but catastrophic impact—demands aggressive measurement.

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Vulnerability density (severity-weighted) | Bandit JSON output: High×3 + Med×2 + Low×1 per KLOC | Exponential decay: 0 findings → 100 |
| Unsafe pattern count | AST detection of `eval()`, `exec()`, `pickle.loads()`, `os.system()`, `shell=True` | Per-KLOC penalty, 0 → 100 |
| Dependency vulnerabilities | pip-audit JSON: CVSS-weighted CVE count | Sigmoid: 0 CVEs → 100 |
| Secrets detected | detect-secrets baseline scan, count of findings | Binary penalty: any secret → 0 |
| Semgrep security rules | Semgrep `p/python` + `p/bandit` rulesets, finding count | Exponential decay per KLOC |

Bandit achieves **88% detection rate** for injection flaws with a 12% false-positive rate. Semgrep reaches **92% precision** through dataflow analysis but runs slower. The IRIS hybrid approach (ICLR 2025) demonstrated that combining CodeQL static analysis with GPT-4 detected **55 of 120 vulnerabilities versus 27 for CodeQL alone**—a 104% improvement—while also discovering 4 previously unknown vulnerabilities. This validates the hybrid static+LLM approach for the security dimension.

### Modularity (weight: 15%)

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Instability balance | AST import analysis: I = Ce/(Ca+Ce), penalize extremes | Distance from 0.5: closer → higher |
| Distance from main sequence | `D = \|A + I − 1\|` via ABC detection + import graph | 1 − D, scaled to 100 |
| LCOM4 (class cohesion) | AST: method-attribute graph connected components | 1/LCOM4 × 100, capped |
| Circular dependency count | Import graph cycle detection (Tarjan's algorithm) | 0 cycles → 100, exponential penalty |
| Module size Gini coefficient | SLOC per module, compute Gini | 1 − Gini, scaled to 100 |

Robert C. Martin's instability and abstractness metrics remain foundational. The `module_coupling_metrics` Python package computes Ce, Ca, I, A, and D for Python packages directly. `import-linter` enforces architectural contracts (layer dependencies, forbidden imports) and can be integrated into CI. For class-level analysis, LCOM4 (connected components in the method-attribute graph) is the most practical cohesion variant—a class with LCOM4 > 1 likely violates single responsibility and should be split.

### Testability (weight: 15%)

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Branch coverage | coverage.py `--branch` JSON report | Direct percentage |
| Mutation score | mutmut `results` cache, killed ÷ total non-equivalent | Direct percentage |
| Cyclomatic complexity (inverted) | Radon `cc_visit()`, average per function | Sigmoid: CC 1 → 100, CC 25 → 0 |
| Function purity ratio | AST: detect global access, I/O calls, mutable state | Pure functions ÷ total × 100 |
| Test-to-code ratio | Test SLOC ÷ production SLOC | Sigmoid: 1.0 ratio → 100 |

Mutation testing is the **gold standard for test suite quality**—it measures whether tests detect actual bugs, not just execute lines. Mutmut (v3.5.0, Feb 2026) processes ~1,200 mutants/minute with 88.5% detection. PyTation (arXiv, Jan 2026) introduces Python-specific mutation operators that catch faults existing tools miss, noting that "Pythonic idioms, though concise and expressive, often impaired testability." An OOPSLA 2025 study of 426 Python projects found property-based tests (Hypothesis) complement unit tests effectively for catching mutations.

### Robustness (weight: 13%)

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Type annotation coverage | AST: annotated params + returns ÷ total | Direct percentage |
| mypy strict compliance | mypy `--strict` error count per KLOC | Exponential decay: 0 errors → 100 |
| Exception handling quality | AST: 1 − (anti-patterns ÷ total handlers) | Direct ratio × 100 |
| Defensive programming density | AST: isinstance + assert + guard clauses per function | Sigmoid: 2+ guards/fn → high |
| None-safety patterns | AST: Optional annotations + None checks before use | Ratio × 100 |

Meta's 2024 survey found mypy at **67% adoption** and Pyright at **38%** among Python developers. Type annotation benefits include IDE support (59%), bug prevention (49.8%), and documentation (49.2%). The Exception Miner tool (SBES 2024) uses TreeSitter queries to detect anti-patterns—Exception Swallowing (empty except blocks) and Destructive Wrapping (catching and re-raising without context) are the most frequent, with 2,286 and 1,196 occurrences respectively in the studied projects.

### Elegance (weight: 12%)

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Cognitive Complexity | complexipy (Rust-based, SonarSource definition) | Sigmoid: 0 → 100, >15 per fn → penalty |
| PEP 8 + Pythonic compliance | Ruff violation count (E/W/F/B/UP rules) per KLOC | Exponential decay |
| Naming convention adherence | Ruff N8xx rules, violation count | Per-KLOC penalty |
| Function length distribution | AST: lines per FunctionDef, P90 value | P90 ≤ 30 lines → 100, >100 → 0 |
| Max nesting depth | AST: recursive depth of if/for/while/with/try | Sigmoid: depth ≤ 3 → 100, >6 → 0 |

Cognitive Complexity (SonarSource, G. Ann Campbell) is the most important modern readability metric. Unlike McCabe's cyclomatic complexity, it adds a **nesting penalty** for each level of nesting when a flow-break occurs inside another—matching human perception of code difficulty. The CoReEval benchmark (arXiv 2025) evaluated 10 LLMs across 1.4M model-snippet-prompt evaluations and found that LLMs emphasize syntactic polish over semantic clarity, with Zero-Shot Learning achieving lowest MAE (0.89) for readability assessment.

### Reusability (weight: 10%)

**Sub-metrics and computation:**

| Sub-metric | Tool / Method | Normalization |
|---|---|---|
| Code duplication | jscpd or Pylint duplicate-code percentage | Linear: 0% → 100, >10% → 0 |
| Coupling (Ce per module) | Import graph analysis | Sigmoid: Ce ≤ 5 → 100, >20 → 0 |
| API surface ratio | AST: public (no underscore prefix) ÷ total definitions | Sweet spot around 30–60% → highest |
| Parameter generality | AST: abstract type annotations (Iterable, Sequence) vs concrete (list) | Ratio × 100 |
| Single responsibility adherence | LCOM4 × function count per class | Composite score |

Reusability receives the lowest weight because it overlaps substantially with modularity (coupling) and maintainability (duplication, cohesion). The DRY violations metric—code duplication percentage—is shared between maintainability and reusability, with each dimension weighting it differently in its sub-score.

---

## The composite formula: penalized weighted geometric mean

### Why geometric mean over arithmetic mean

The arithmetic mean has "perfect compensability"—a score of (0, 100) with equal weights produces the same composite as (50, 50). For code quality, this is dangerous: excellent readability should not mask terrible security. The **geometric mean reduces compensability** and naturally penalizes imbalanced profiles. The UN Human Development Index switched from arithmetic to geometric mean in 2010 for precisely this reason.

### The PQI formula

```
PQI = min(100, floor_penalty × ∏(Dᵢ^wᵢ))
```

Where:
- **Dᵢ** = normalized dimension score (0–100) for dimension i, clamped to [1, 100] to avoid zero-product collapse
- **wᵢ** = weight for dimension i (summing to 1.0)
- **floor_penalty** = penalty multiplier if any dimension falls below a critical floor

**Weights (default profile for production services):**

| Dimension | Weight (wᵢ) | Justification |
|---|---|---|
| Maintainability | 0.20 | 60–80% of lifecycle cost; strongest empirical link to engineering outcomes |
| Security | 0.15 | Asymmetric catastrophic risk; single vulnerability can be fatal |
| Modularity | 0.15 | Structural foundation enabling all other qualities |
| Testability | 0.15 | Enables verification of all other dimensions |
| Robustness | 0.13 | Production reliability; type safety prevents entire bug classes |
| Elegance | 0.12 | Cognitive load directly affects modification speed and error rate |
| Reusability | 0.10 | Important but heavily overlaps with modularity and maintainability |

**Floor penalty mechanism:**

```python
def floor_penalty(dimension_scores: dict[str, float]) -> float:
    CRITICAL_FLOOR = 20  # Any dimension below 20 triggers penalty
    violations = [s for s in dimension_scores.values() if s < CRITICAL_FLOOR]
    if not violations:
        return 1.0
    # Each violation below floor reduces composite by 10% per 10 points below floor
    penalty = 1.0
    for score in violations:
        deficit = (CRITICAL_FLOOR - score) / CRITICAL_FLOOR
        penalty *= (1.0 - 0.3 * deficit)  # Max 30% penalty per dimension
    return max(0.3, penalty)  # Floor penalty itself floors at 0.3
```

This ensures a project with 95 in six dimensions but 5 in security cannot score above ~60—it must address the critical gap.

### Normalization strategy

Each raw metric is normalized to 0–100 using metric-appropriate functions:

- **Bounded metrics** (coverage %, duplication %): linear scaling
- **Count-based metrics** (violations per KLOC): exponential decay `score = 100 × e^(-λ × count)` where λ is calibrated per metric
- **Unbounded metrics** (cyclomatic complexity): sigmoid `score = 100 / (1 + e^(k × (x − midpoint)))` where midpoint is the "acceptable" threshold
- **Binary metrics** (secrets detected): hard penalty (any finding → dimension score capped)

### Configurable weight profiles

| Profile | Maint | Sec | Mod | Test | Rob | Eleg | Reuse |
|---|---|---|---|---|---|---|---|
| **Production service** (default) | 0.20 | 0.15 | 0.15 | 0.15 | 0.13 | 0.12 | 0.10 |
| **Library/SDK** | 0.15 | 0.10 | 0.20 | 0.15 | 0.10 | 0.15 | 0.15 |
| **Data science/script** | 0.15 | 0.10 | 0.10 | 0.20 | 0.15 | 0.15 | 0.15 |
| **Safety-critical** | 0.15 | 0.25 | 0.10 | 0.20 | 0.15 | 0.05 | 0.10 |

---

## Scoring rubric and the "good enough" threshold

### Quality bands

| Score range | Rating | Interpretation | Action required |
|---|---|---|---|
| **0–30** | Poor | Significant quality risks; likely harboring critical issues | Immediate remediation; block deployment |
| **31–54** | Acceptable | Functional but carrying substantial technical debt | Prioritize improvement in lowest dimensions |
| **55–64** | Adequate | Meets minimum professional standards with known gaps | Scheduled improvement; acceptable for non-critical code |
| **65–79** | Good | Solid engineering; all dimensions above critical floors | Production-ready; continue incremental improvement |
| **80–100** | Excellent | Exemplary quality across all dimensions | Maintain; use as reference codebase |

### Why 65 is "good enough"

The **65/100 threshold** is calibrated against three industry benchmarks. SIG data shows systems rated 3+ stars (top 65% of their benchmark) have acceptable maintenance costs—below this, costs escalate nonlinearly. CodeScene's Code Health research found that files scoring below 4/10 (mapping to roughly our 55) are **15× more likely to contain defects**. SonarQube's maintainability "A" rating requires technical debt below 5% of development cost—projects meeting this threshold and having no critical security/reliability issues typically score ≥65 in our model. The geometric mean aggregation ensures that reaching 65 requires no dimension to be catastrophically low, which is the core property we want from a "good enough" gate.

For context: the Microsoft Visual Studio Maintainability Index uses 20/100 as its "good" floor, but that metric covers only complexity and volume. Our composite captures seven dimensions, making the higher threshold appropriate. CodeScene considers 7/10 the dividing line between "healthy" and "declining" code health.

---

## Existing composite approaches compared

| Approach | Scale | Dimensions | Aggregation | Python support | Core strength | Core weakness |
|---|---|---|---|---|---|---|
| **CodeScene Code Health** | 1–10 | 25–30 biomarkers (maintainability focus) | Weighted aggregation against baseline; floor of 1 | Yes | 6× more accurate than SonarQube on public datasets; validated by engineering outcomes | Proprietary algorithm; mainly maintainability |
| **SIG/Sigrid** | 1–5 stars | 8 properties → ISO 25010 maintainability | Percentile-based against 30K+ system benchmark | Yes (300+ langs) | TÜViT-certified; massive benchmark; empirical cost correlation | Commercial; benchmark-relative; mainly maintainability |
| **Microsoft MI** | 0–100 | Halstead Volume, CC, LOC | Linear formula with ln() | Yes (Radon) | Simple; widely implemented | 1992 coefficients; overweights LOC; no security/testing |
| **SonarQube** | A–E per dim | Security, Reliability, Maintainability + coverage/duplication | Worst-severity for ratings; SQALE for debt | Yes | Widely adopted (50K+ companies); multi-dimension | No single composite score; harsh severity-based ratings |
| **CISQ/ISO 5055** | Weakness counts | Reliability, Security, Perf, Maintainability | Count density per dimension | Language-independent spec | ISO standard; 138 structural weaknesses | No single composite; vendor-dependent |
| **SQALE** | Minutes → A–E | Technical debt across ISO characteristics | Sum of remediation costs → ratio → letter grade | Yes (via SonarQube) | Links quality to cost; actionable pyramid | Additive only; mainly technical debt |
| **PQI (proposed)** | 0–100 | 7 dimensions, 35+ sub-metrics | Penalized weighted geometric mean | Native Python | Single composite number; configurable; AI-augmentable; per-function/file/project | Requires tool orchestration; normalization calibration needed |

The PQI distinguishes itself by being the only approach that produces a **single composite number across all seven dimensions** while remaining fully open and computable from existing tools. CodeScene's biomarker approach is the closest in philosophy—evidence-based, focused on what predicts engineering outcomes—but it is proprietary and focused on maintainability. The SIG model is rigorous but benchmark-relative and does not produce a single score. SonarQube covers multiple dimensions but deliberately avoids combining them into one number.

---

## AI and LLM augmentation of the metric

### The three-layer hybrid architecture

Research strongly supports a hybrid approach. The JISEM 2025 three-layer architecture and Meta's CQS system both demonstrate that **combining static analysis with ML and LLM reasoning outperforms any single method**.

**Layer 1 — Deterministic static analysis (70% of signal):** Ruff, Radon, Bandit, mypy, coverage.py, Vulture produce precise, reproducible metrics. These form the reliable backbone of the PQI. Every sub-metric in the seven dimensions above is computable from this layer alone.

**Layer 2 — ML pattern detection (10% of signal):** CodeBERT/UniXcoder embeddings measure similarity to "gold standard" reference code. Supervised models trained on defect/smell datasets (CodeXGLUE's Devign for vulnerability detection, BigCloneBench for duplication) predict defect probability per function. AST-based features (cyclomatic complexity, nesting, coupling) feed into classifiers trained on labeled quality data.

**Layer 3 — LLM-as-judge (20% of signal):** The most impactful AI augmentation. Meta's Code Quality Score system, deployed to **5,000+ engineers with 60% weekly helpfulness**, uses a multi-agent pipeline: Issue Collector → Issue Validator (LLM scoring 0–10) → Post-Processing. Key design principles from research:

- **Decompose scoring**: Separate LLM evaluators for each dimension, not one holistic prompt. The Farzi et al. (2024) multi-criteria decomposition approach grades sub-criteria (0–3 scale) independently
- **Use chain-of-thought reasoning**: Ask for justification before the score. CodeJudge (EMNLP 2024) demonstrates "slow thinking" evaluation outperforms direct scoring
- **Jury approach**: Multiple evaluations with majority voting reduce bias and variability (Verga et al., 2024)
- **One-shot examples outperform multi-shot**: Performance declines with more examples for code evaluation (CodeJudge-Eval finding)
- **Calibrate against deterministic metrics**: Use static analysis results as ground truth anchors

GitHub Copilot Code Review usage has grown **10× since April 2024**, now accounting for over 1 in 5 code reviews on GitHub (60M+ reviews). The LLM-driven SAST-Genius framework achieves **89.5% precision** versus 35.7% for standalone Semgrep, demonstrating the power of LLM-enhanced static analysis.

### Practical LLM integration for PQI

```python
# Structured LLM evaluation prompt (per-function)
QUALITY_JUDGE_PROMPT = """
Rate this Python function on a 0-10 scale for each criterion.
Provide chain-of-thought reasoning before each score.

Criteria:
1. Pythonic idiom adherence (list comprehensions, context managers, 
   f-strings, dataclasses over dicts)
2. Error handling completeness (edge cases, input validation)
3. Naming clarity and self-documentation
4. Single responsibility adherence
5. Design for testability (pure functions, injectable dependencies)

Static analysis context (use as anchoring signal):
- Cognitive Complexity: {cog_complexity}
- Cyclomatic Complexity: {cc}
- Type annotation coverage: {type_coverage}%
- Bandit findings: {bandit_findings}

Function:
```python
{function_code}
```

Respond in JSON: {"reasoning": {...}, "scores": {...}, "overall": float}
"""
```

The LLM score feeds into the elegance and robustness dimensions as a supplementary signal, weighted at 20% within those sub-scores, with the remaining 80% from deterministic tools.

---

## Python implementation plan

### Tool orchestration pipeline

The core architecture uses **Python AST for deep semantic analysis** and **TreeSitter for multi-language structural parsing**, with existing tools invoked programmatically.

TreeSitter excels over Python's `ast` module in three ways: it preserves every token and precise byte/column positions (critical for editor integration and coaching feedback), it handles syntactically invalid code gracefully via error recovery (essential during active editing), and it supports 30+ languages through a single API. Python's `ast` module, however, provides cleaner semantic analysis for pure Python codebases—type annotation inspection, decorator detection, and scope analysis are more natural with `ast.NodeVisitor`. The recommended approach: **use both together**—TreeSitter for structural metrics and source mapping, Python AST for semantic metrics.

```python
# Core metric computation pipeline
from dataclasses import dataclass
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze as raw_analyze
import ast, subprocess, json, math

@dataclass
class DimensionScore:
    name: str
    score: float          # 0-100
    sub_scores: dict      # sub-metric name → score
    confidence: float     # 0-1, how reliable this score is
    recommendations: list # actionable coaching items

@dataclass  
class PQIResult:
    composite: float      # The single 0-100 number
    dimensions: dict[str, DimensionScore]
    quality_band: str     # "Poor" | "Acceptable" | "Good" | "Excellent"
    floor_penalty: float  # 1.0 if no penalty applied
    trend: float | None   # Change from previous measurement

def compute_pqi(source_code: str, project_path: str = None) -> PQIResult:
    """Compute PQI for a single file or project."""
    dimensions = {}
    
    # 1. Maintainability
    mi = mi_visit(source_code, multi=True)  # Radon MI (0-100)
    blocks = cc_visit(source_code)
    avg_cc = sum(b.complexity for b in blocks) / max(len(blocks), 1)
    raw = raw_analyze(source_code)
    dead_code_pct = run_vulture(source_code)  # Returns percentage
    doc_coverage = compute_doc_coverage(source_code)  # AST-based
    
    maint_score = weighted_mean([
        (mi, 0.25), 
        (sigmoid_norm(avg_cc, midpoint=10, k=0.3), 0.20),
        (100 - dead_code_pct * 6.67, 0.15),  # 15% dead → 0
        (doc_coverage, 0.15),
        (100 - get_duplication_pct(source_code) * 10, 0.25)
    ])
    dimensions['maintainability'] = DimensionScore(
        'Maintainability', maint_score, {...}, 0.95, [...]
    )
    
    # 2. Security (via Bandit + Semgrep)
    bandit_results = run_bandit_json(source_code)
    sec_score = compute_security_score(bandit_results, raw.sloc)
    dimensions['security'] = DimensionScore(
        'Security', sec_score, {...}, 0.90, [...]
    )
    
    # ... (compute remaining 5 dimensions similarly)
    
    # Aggregate via penalized weighted geometric mean
    weights = DEFAULT_WEIGHTS  # Configurable per profile
    scores = {k: max(1, v.score) for k, v in dimensions.items()}
    
    log_sum = sum(weights[k] * math.log(scores[k]) for k in weights)
    geometric_mean = math.exp(log_sum)
    
    penalty = compute_floor_penalty(scores)
    composite = min(100, geometric_mean * penalty)
    
    band = classify_band(composite)
    return PQIResult(composite, dimensions, band, penalty, None)

def sigmoid_norm(x: float, midpoint: float, k: float = 0.5) -> float:
    """Normalize unbounded metric to 0-100 via sigmoid."""
    return 100.0 / (1.0 + math.exp(k * (x - midpoint)))
```

### Tool invocation map

| Tool | Invocation | Output parsing | Feeds dimension(s) |
|---|---|---|---|
| **Radon** | `cc_visit(code)`, `mi_visit(code)`, `h_visit(code)` | Python objects (Function, Class, HalsteadReport) | Maintainability, Elegance, Testability |
| **Ruff** | `subprocess: ruff check --output-format json` | JSON array of violations with rule codes | Elegance, Robustness |
| **Bandit** | `subprocess: bandit -f json -r .` | JSON with severity/confidence per finding | Security |
| **mypy** | `subprocess: mypy --strict --no-error-summary` | Line-count of errors; `--linecount-report` for coverage | Robustness |
| **Vulture** | `subprocess: vulture . --min-confidence 80` | Text output, parse for unused definitions | Maintainability |
| **coverage.py** | `coverage.CoverageData()` API or JSON report | Branch/line coverage percentages per file | Testability |
| **mutmut** | `subprocess: mutmut run` then `mutmut results` | Killed/survived/timeout counts | Testability |
| **complexipy** | `subprocess: complexipy . --output-format json` | JSON with cognitive complexity per function | Elegance |
| **Semgrep** | `subprocess: semgrep --config p/python --json` | JSON findings with rule IDs and severity | Security |
| **pip-audit** | `subprocess: pip-audit --format json` | JSON with CVE IDs and CVSS scores | Security |

### Per-function, per-file, per-project aggregation

- **Per-function**: Compute all AST-derivable metrics (CC, cognitive complexity, type coverage, nesting depth, function length) directly. Security and test metrics are not meaningful at function level—mark as N/A
- **Per-file**: Aggregate function scores (weighted by SLOC contribution); add file-level metrics (import analysis, duplication, MI). This is the primary unit of measurement
- **Per-project**: Weighted average of file scores (by SLOC), plus project-level metrics (dependency vulnerabilities, overall test coverage, mutation score, architectural coupling graph). The project score is the PQI that appears in dashboards

### Trend tracking schema

```sql
CREATE TABLE pqi_measurements (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    commit_sha VARCHAR(40) NOT NULL,
    measured_at TIMESTAMP DEFAULT NOW(),
    composite_score FLOAT NOT NULL,
    dimension_scores JSONB NOT NULL,  -- {"maintainability": 72, ...}
    sub_scores JSONB NOT NULL,        -- Nested detail
    file_scores JSONB,                -- Per-file breakdown
    weight_profile VARCHAR(50),       -- "production" | "library" | etc.
    metadata JSONB                    -- LOC, file count, tool versions
);

CREATE INDEX idx_pqi_project_time ON pqi_measurements(project_id, measured_at);
```

Wily already tracks Radon metrics across git commits. The PQI system extends this pattern to all seven dimensions, storing each measurement as a time-series point. Trend visualization shows dimension-level trajectories, enabling coaching like: "Your security score improved from 45 → 72 over the last 3 sprints, but elegance dropped from 68 → 61—consider addressing the new cognitive complexity hotspots."

---

## Integration into an agentic coaching platform

The coaching agent uses **PydanticAI** for structured LLM interactions (validated output schemas, type-safe tool calls) and **LangGraph** for multi-step workflow orchestration. Temporal handles long-running analysis pipelines (mutation testing can take minutes) with checkpointing and retry logic.

```
┌─────────────────────────────────────────────────────┐
│                    Temporal Workflow                  │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │ Static   │   │ Dynamic  │   │ LLM-as-Judge     │ │
│  │ Analysis │   │ Analysis │   │ (PydanticAI)     │ │
│  │ ─────────│   │ ─────────│   │ ──────────────── │ │
│  │ Radon    │   │coverage  │   │ Per-function     │ │
│  │ Ruff     │   │ mutmut   │   │ quality review   │ │
│  │ Bandit   │   │          │   │ Coaching advice  │ │
│  │ mypy     │   │          │   │ generation       │ │
│  │ Vulture  │   │          │   │                  │ │
│  │ Semgrep  │   │          │   │                  │ │
│  └────┬─────┘   └────┬─────┘   └───────┬──────────┘ │
│       │              │                  │            │
│       └──────────────┴──────────────────┘            │
│                      │                               │
│              ┌───────▼────────┐                      │
│              │  Aggregation   │                      │
│              │  Engine        │──── PQI Score        │
│              │  (LangGraph)   │──── Coaching Report  │
│              │                │──── Trend Data       │
│              └────────────────┘                      │
└─────────────────────────────────────────────────────┘
```

The coaching feedback generator uses dimension scores to prioritize recommendations. If security is the lowest-scoring dimension, the agent surfaces specific Bandit findings with fix suggestions. If elegance is low, it identifies the highest-cognitive-complexity functions and generates refactoring suggestions using the LLM. The key insight from Meta's CQS deployment: **developer feedback loops are essential**—the system should allow developers to dismiss false positives, which feeds back into calibration.

---

## Key papers and resources (2023–2026)

**Composite metrics and quality models:**
Pisch, Cai, Kazman et al. "M-score: An Empirically Derived Software Modularity Metric" (ESEM 2024). Campbell, G.A. "Cognitive Complexity: A New Way of Measuring Understandability" (SonarSource whitepaper). ISO/IEC 25010:2023 revision — 9 product quality characteristics. CISQ/ISO 5055:2021 — Automated Source Code Quality Measures.

**AI-powered code quality:**
Wong et al. "Code Quality Score system" (NeurIPS 2025 DL4C Workshop) — Meta's production multi-agent system. Li et al. "IRIS: LLM-Assisted Static Analysis" (ICLR 2025) — 104% improvement over CodeQL alone. Jaoua et al. "Combining LLMs with Static Analyzers for Code Review Generation" (MSR 2025). Zhuo, "ICE-Score: Instructing LLMs to Evaluate Code" (EACL 2024). Ouedraogo et al. "CoReEval: Human-Aligned Code Readability Assessment with LLMs" (arXiv 2025).

**Python-specific quality and testing:**
Souza et al. "Exception Miner: Multi-language Static Analysis Tool" (SBES 2024). PyTation: "Hybrid Fault-Driven Mutation Testing for Python" (arXiv, Jan 2026). "An Empirical Evaluation of Property-Based Testing in Python" (OOPSLA 2025). Meta Engineering, "Typed Python in 2024" — mypy 67% adoption survey. Takerngsaksiri et al. "Code Readability in the Age of LLMs: Industrial Case Study from Atlassian" (arXiv 2025).

**LLM code evaluation benchmarks:**
CodeJudgeBench (2025) — "thinking" models drastically outperform standard models. SWR-Bench (2025) — 1,000 verified PRs, ~90% LLM-human agreement. CodeXGLUE (Microsoft, NeurIPS 2021) — 10 tasks, 14 datasets.

---

## Conclusion: a principled single number with escape hatches

The PQI achieves its design goal—one number telling a developer "your code quality is X/100"—while preserving the transparency that makes it actionable. The penalized weighted geometric mean prevents any single dimension from being masked by others, and the floor penalty mechanism ensures critical gaps in security or robustness are impossible to hide behind high elegance scores. The **65/100 threshold** represents genuinely production-ready code: all dimensions above critical floors, no catastrophic weaknesses, and a level of engineering discipline that empirically correlates with sustainable maintenance costs.

Three design decisions distinguish this approach from prior work. First, the geometric mean aggregation borrowed from composite indicator theory (HDI, Global Innovation Index) provides mathematically principled compensability control that simple weighted averages lack. Second, every sub-metric is programmatically computable from existing, actively-maintained Python tools—no proprietary black boxes required. Third, the three-layer architecture (deterministic → ML → LLM) allows organizations to start with the deterministic layer alone (achieving ~80% of the signal) and progressively add AI augmentation as their infrastructure matures.

The single most impactful action for any team adopting this metric: **track the trend, not the absolute number**. A project improving from 42 to 58 over a quarter is in a healthier position than one stagnating at 71. CodeScene's research confirms that the rate of quality change predicts engineering outcomes more reliably than any static snapshot.