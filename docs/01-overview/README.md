# Getting Started

## Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <project-name>
```

### 2. Backend Setup

**Option A: uv (Recommended for BFF/Web)**

```bash
# Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create environment and install
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

**Option B: conda (For data-heavy projects)**

```bash
conda create -n project python=3.12
conda activate project
pip install -r requirements.txt  # Or use environment.yml if available
```

See [Python Environment Management](../04-references/architecture-standards/13-development-workflow.md#python-environment-management) for detailed guidance on when to use each.

# Copy environment file and configure
cp config/.env.example config/.env
# Edit config/.env with your settings
```

### 3. Frontend Setup

```bash
cd modules/frontend
npm install
```

### 4. Database Setup

```bash
# Create database
createdb <database-name>

# Run migrations
cd modules/backend
alembic upgrade head
```

## Running the Application

### Development Mode

```bash
# Backend (from project root)
uvicorn modules.backend.main:app --reload --port 8000

# Frontend (in separate terminal)
cd modules/frontend
npm run dev
```

### Access Points

- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Frontend: http://localhost:5173

## Running Tests

```bash
# All tests
pytest

# By test type
pytest tests/unit                    # Fast, isolated tests
pytest tests/integration             # Tests with real database
pytest tests/e2e                     # Full stack tests

# With coverage
pytest tests/unit --cov=modules/backend

# Specific markers
pytest -m unit
pytest -m integration
```

## Code Quality

```bash
# Format code
black modules/backend tests
isort modules/backend tests

# Lint
flake8 modules/backend tests

# Type check
mypy modules/backend
```
