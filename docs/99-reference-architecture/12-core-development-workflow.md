# 12 - Development Workflow

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic development workflow standard

---

## Context

The gap between "code works on my machine" and "code is reliably deployed to production" is where most teams lose time. Git branching strategies, CI/CD pipelines, dependency management, and release processes all need to be decided once and followed consistently — not reinvented per project or left to individual preference.

The branching model uses `main` (production) and `develop` (integration) with feature and hotfix branches because it balances simplicity with the need for a stable production branch and a safe integration point. CI/CD runs through GitHub Actions with a defined pipeline: lint, test, security scan, build, deploy. Every merge is gated on passing checks — no exceptions.

Environment management standardizes on `uv` for web applications and `conda` for data/ML projects, reflecting the different dependency ecosystems each deals with. Semantic versioning, pre-commit hooks, and a maintained CHANGELOG ensure that releases are predictable, code quality is enforced before commit, and the history of changes is human-readable. This workflow integrates with coding standards (08) for quality gates, testing (11) for CI test execution, and deployment (15, 16) for release automation.

---

## Version Control

### Standard: Git

All projects use Git for version control.

### Repository Structure

One repository per deployable unit:
- Backend service: One repository
- Frontend: Separate repository or monorepo with backend
- Shared libraries: Separate repository

### Branch Strategy

**Main branches:**
- `main`: Production-ready code
- `develop`: Integration branch for features

**Feature branches:**
- Format: `feature/{ticket-id}-{short-description}`
- Branch from: `develop`
- Merge to: `develop` via pull request

**Hotfix branches:**
- Format: `hotfix/{ticket-id}-{short-description}`
- Branch from: `main`
- Merge to: `main` and `develop`

### Commit Messages

Format:
```
[TYPE] Short description (max 72 characters)

Detailed explanation if needed.
- List of changes
- References to tickets

Fixes #123
```

Types:
- `[FEAT]` - New feature
- `[FIX]` - Bug fix
- `[REFACTOR]` - Code restructuring
- `[DOCS]` - Documentation
- `[TEST]` - Tests
- `[CHORE]` - Build, tooling, dependencies

### Pull Request Process

1. Create feature branch
2. Make changes with atomic commits
3. Push branch and create pull request
4. Automated checks run (lint, test)
5. Code review by team member
6. Address feedback
7. Squash and merge when approved
8. Delete feature branch

### Code Review Standards

Reviewers check:
- Code correctness
- Adherence to standards
- Test coverage for changes
- Security implications
- Performance implications

Reviews are constructive. Block only for significant issues.

---

## CI/CD Pipeline

### Standard: GitHub Actions

All projects use GitHub Actions for CI/CD.

### Pipeline Stages

**On Pull Request:**
1. Lint code
2. Run unit tests
3. Run integration tests
4. Check for security vulnerabilities
5. Build artifacts

**On Merge to develop:**
1. All PR checks
2. Deploy to staging environment
3. Run smoke tests

**On Merge to main:**
1. All checks
2. Create release tag
3. Deploy to production
4. Run production smoke tests

### Pipeline Configuration

Store workflow files in `.github/workflows/`:
- `ci.yml` - Pull request checks
- `deploy-staging.yml` - Staging deployment
- `deploy-production.yml` - Production deployment

### Secrets Management

CI/CD secrets stored in GitHub repository secrets:
- Never in workflow files
- Minimal scope (per environment)
- Rotate periodically

---

## Testing

See **11-testing-standards.md** for comprehensive testing guidance.

### Quick Reference

| Category | Purpose | Location |
|----------|---------|----------|
| Unit | Test individual functions/classes | `tests/unit/` |
| Integration | Test component interactions | `tests/integration/` |
| End-to-end | Test complete user flows | `tests/e2e/` |

### CI Pipeline Stages

1. **Unit tests** - Run on every commit (fast feedback)
2. **Integration tests** - Run on every commit (verify interactions)
3. **E2E tests** - Run before deployment (validate critical paths)

### Coverage Requirements

- Critical paths: 100% coverage required
- Business logic: 80% coverage target
- Overall: Focus on critical paths over percentage

---

## Code Quality

### Linting

Python: flake8 + black + isort

Configuration in `pyproject.toml` or respective config files.

Run before commit: `make lint` or equivalent.

### Type Checking

Python: mypy with strict mode

Type hints required for:
- Function signatures
- Class attributes
- Module-level variables

### Pre-commit Hooks

Use pre-commit framework:
```yaml
repos:
  - repo: local
    hooks:
      - id: lint
      - id: format
      - id: typecheck
```

Developers install hooks; CI enforces checks.

### Code Formatting

Automated formatting via black (Python).

No debates about style; formatter decides. Run before commit.

---

## Dependency Management

### Python Dependencies

Use `requirements.txt` for direct dependencies with minimum versions:
```
fastapi>=0.109.0
sqlalchemy>=2.0.25
```

### Version Strategy

- Use `>=` for minimum compatible versions
- Specify upper bounds only when known incompatibilities exist
- Update minimum versions monthly or for security fixes
- Test thoroughly after updates

### Vulnerability Scanning

Automated scanning in CI:
- Python: pip-audit or safety
- Node: npm audit

Block merges with high/critical vulnerabilities in dependencies.

---

## Documentation

### Code Documentation

Required documentation:
- Module docstrings explaining purpose
- Public function docstrings with args, returns, raises
- Complex logic explained with comments
- Non-obvious decisions explained

### API Documentation

OpenAPI/Swagger generated automatically from code.

Additional documentation for:
- Authentication flows
- Error codes and meanings
- Rate limits and quotas

### Architecture Documentation

Maintain in `docs/` directory:
- Architecture decisions (ADRs)
- Deployment guides
- Runbooks

Update documentation with code changes.

---

## Versioning

### Semantic Versioning

All projects use semantic versioning: `MAJOR.MINOR.PATCH`

- MAJOR: Breaking changes
- MINOR: New features, backwards compatible
- PATCH: Bug fixes, backwards compatible

### Release Process

1. Update version in code
2. Update CHANGELOG.md
3. Create git tag: `v1.2.3`
4. CI builds and deploys

### Changelog

Maintain CHANGELOG.md with:
- Version and date
- Changes categorized (Added, Changed, Fixed, Removed)
- Breaking change warnings

---

## Development Environment

### Local Setup

Projects include:
- `README.md` with setup instructions
- `requirements.txt` for Python dependencies
- `.env.example` with required environment variables
- `Makefile` or scripts for common tasks

### Python Environment Management

Choose the environment manager based on project type:

#### Option 1: uv (Recommended for Web Applications)

Use **uv** for BFF, API services, and web applications.

**Why uv:**
- 10-100x faster than pip
- Built-in lock files for reproducibility
- Python version management included
- Simple pip-compatible workflow

**Setup:**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create environment and install
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Create lock file for reproducibility
uv pip compile requirements.txt -o requirements.lock
uv pip sync requirements.lock
```

**Project files:**
```
project/
├── .python-version        # Pin Python version
├── .venv/                 # Virtual environment
├── requirements.txt       # Source dependencies
└── requirements.lock      # Locked versions (generated, committed)
```

#### Option 2: conda (Recommended for Data/ML)

Use **conda** for data science, backtesting, analytics, and ML projects.

**Why conda:**
- MKL-optimized numpy/scipy/pandas (2-10x faster linear algebra)
- Pre-built CUDA/cuDNN for GPU (PyTorch, TensorFlow)
- Manages non-Python dependencies (C libraries, CUDA toolkit)
- Binary compatibility guaranteed

**Setup:**
```bash
# Create environment from file
conda env create -f environment.yml

# Or create manually
conda create -n project python=3.12
conda activate project
conda install numpy pandas scikit-learn

# Export for reproducibility
conda env export > environment.yml
```

**Project files:**
```
project/
├── environment.yml        # Conda environment definition
└── ...
```

**environment.yml example:**
```yaml
name: project
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.12
  - numpy
  - pandas
  - scikit-learn
  - pytorch
  - cudatoolkit=11.8
  - pip
  - pip:
    - some-pip-only-package
```

#### Decision Matrix

| Project Type | Recommended | Reason |
|--------------|-------------|--------|
| BFF / Web API | uv | Fast installs, no native deps needed |
| REST microservices | uv | Simpler, faster CI/CD |
| Backtesting engine | conda | MKL-optimized pandas/numpy |
| ML model training | conda | CUDA/cuDNN pre-built |
| Data pipelines | conda | Optimized numerical libs |
| CLI tools | uv | Simple deployment |

#### Performance Comparison

```
numpy matrix multiply (1000x1000):
├── pip/uv numpy (OpenBLAS):     ~150ms
└── conda numpy (MKL):           ~25ms   ← 6x faster

pandas groupby (10M rows):
├── pip/uv pandas:               ~800ms
└── conda pandas (MKL):          ~200ms  ← 4x faster
```

#### Hybrid Projects

For projects with both web and data components (e.g., trading platform):

```
trading-platform/
├── services/
│   ├── bff-api/              # uv - web layer
│   └── market-data/          # uv - simple ingestion
├── analytics/
│   ├── backtester/           # conda - heavy numerical
│   └── signals/              # conda - ML models
└── ...
```

Each component has its own environment matching its needs.

#### Anti-Patterns

- **Don't mix pip and conda** in the same environment (breaks linkage)
- **Don't use conda for pure web apps** (slower, no benefit)
- **Don't use pip for GPU ML** (manual CUDA setup is painful)

### Environment Parity

Development environment matches production:
- Same database version
- Same Redis version
- Same Python version

### Local Services

For local development:
- PostgreSQL: Install locally or use cloud dev instance
- Redis: Install locally
- External services: Use sandbox/test accounts

---

## Workflow Automation

### Makefile Commands

Standard commands available in all projects:
```makefile
make install     # Install dependencies
make lint        # Run linters
make format      # Format code
make test        # Run tests
make run         # Start development server
make clean       # Clean build artifacts
```

### Development Server

Hot reload enabled for development:
- Python: uvicorn with --reload
- Frontend: Vite HMR

### Database Migrations

Development workflow:
1. Create migration: `alembic revision --autogenerate -m "description"`
2. Review generated migration
3. Apply: `alembic upgrade head`
4. Test rollback: `alembic downgrade -1`
5. Commit migration file

Never auto-generate in production. Generate locally, review, commit.
