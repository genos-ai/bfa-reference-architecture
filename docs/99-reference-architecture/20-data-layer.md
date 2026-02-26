# 20 - Data Layer (Optional Module)

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.1.0 (2025-01-29): Added file-based data storage section (data/ directory)
- 1.0.0 (2025-01-27): Initial generic data layer standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project needs:
- Time-series data storage
- Complex analytics
- Advanced caching strategies
- Multiple database types

For basic CRUD applications, PostgreSQL with SQLAlchemy (covered in 03-backend-architecture.md) is sufficient.

---

## Context

Most projects start with PostgreSQL and SQLAlchemy for standard CRUD operations, and the backend architecture (03) already covers that baseline. This optional module exists for projects that outgrow basic relational storage — when they need time-series data, analytical queries across large datasets, advanced caching, or structured file storage.

The design decision is to keep PostgreSQL as the single source of truth while adding specialized tools for specialized workloads: TimescaleDB (a PostgreSQL extension) for time-series data, DuckDB (embedded, zero-config) for analytical queries over Parquet files, and Redis for ephemeral caching. Each technology handles a specific data shape better than PostgreSQL alone, without introducing a separate database server or significant operational overhead.

The file-based data section (`data/` directory) standardizes how projects handle datasets, exports, and cached artifacts — areas where ad-hoc approaches quickly create sprawling, undocumented file hierarchies. This module connects to module structure (04) through the rule that each module owns its tables, to observability (10) for data pipeline monitoring, and to background tasks (14) for scheduled data processing.

---

## Core Database: PostgreSQL

All projects use PostgreSQL as the primary relational database.

Rationale:
- Mature, battle-tested at scale
- Excellent JSON support for flexible schemas
- Strong consistency guarantees
- Extensive tooling and AI training data

Version: PostgreSQL 16 or latest stable

---

## Optional: Time-Series Extension (TimescaleDB)

### When to Adopt

Adopt TimescaleDB when storing:
- Sensor readings
- Event logs
- Metrics and monitoring data
- Any timestamped data queried by time range

### Rationale

- Single database system to manage
- Native PostgreSQL compatibility (same queries, same tools)
- Automatic partitioning (hypertables)
- Compression for historical data
- Continuous aggregates for pre-computed rollups

### Hypertable Configuration

TimescaleDB hypertables use these defaults:
- Chunk interval: 1 day for high-frequency data, 1 week for daily data
- Compression: Enable after 7 days
- Retention: Configure per table based on requirements

### Continuous Aggregates

Pre-compute common aggregations:
- Hourly summaries from raw data
- Daily summaries from hourly
- Weekly/monthly for dashboards

Refresh policies run automatically on schedule.

---

## Optional: Analytics Engine (DuckDB)

### When to Adopt

Adopt DuckDB when performing:
- Complex analytical queries over large datasets
- Historical analysis across years of data
- Batch processing and aggregations
- Data exploration and research

### Rationale

- Columnar storage optimized for analytics
- Reads Parquet files directly
- No server required (embedded)
- Complements PostgreSQL for different query patterns

### Usage Pattern

1. Export relevant data to Parquet files
2. Query with DuckDB for analysis
3. Store results back in PostgreSQL if needed

---

## Cache and Ephemeral Data: Redis

### Standard Usage

Redis handles caching, pub/sub, and ephemeral data.

Use cases:
- API response caching
- Session storage (when not using JWT)
- Rate limiting counters
- Task queue backend
- Pub/sub for real-time updates

### Configuration

Key settings:
- maxmemory: Set based on available RAM
- maxmemory-policy: allkeys-lru
- appendonly: yes (if persistence needed)

### Cache Strategy

**Cache Layers:**
1. Application cache - In-process, short TTL
2. Redis cache - Shared across processes, medium TTL

**Cache Keys:**
Format: `{service}:{entity}:{identifier}:{version}`
Example: `users:profile:user-123:v1`

Include version to enable safe schema changes.

**Invalidation:**
- User data: Invalidate on write
- Configuration: TTL-based, short duration
- Computed results: Invalidate on source data change

---

## Data Architecture by Type

### Relational Data

Definition: Data with relationships, requiring ACID transactions.

Examples: Users, accounts, orders, configurations.

Storage: PostgreSQL

Access pattern: ORM (SQLAlchemy) for CRUD, raw SQL for complex queries.

### Time-Series Data (Optional)

Definition: Timestamped data points, append-mostly, queried by time range.

Examples: Metrics, events, sensor data.

Storage: TimescaleDB (PostgreSQL extension)

Access pattern: Raw SQL with time-bucket functions.

### Analytical Data (Optional)

Definition: Large datasets queried for patterns, aggregations.

Examples: Historical reports, analytics datasets.

Storage: Parquet files queried via DuckDB.

Access pattern: DuckDB queries in separate analysis process.

### Ephemeral Data

Definition: Temporary data that can be regenerated.

Examples: Cached responses, session data, rate limit counters.

Storage: Redis

TTL required: All ephemeral data must have expiration.

### File-Based Data

Definition: Large datasets stored as files, not in database.

Examples: Historical market data, training datasets, bulk exports.

Storage: `data/` directory in project root.

Access pattern: Direct file I/O or DuckDB for queries.

See **13-project-template.md** for directory structure details.

---

## File-Based Data Storage

For projects handling large datasets (trading data, ML training sets, analytics), use the `data/` directory structure.

### Directory Structure

```
data/
├── raw/          # Original source data (downloads, API exports)
├── processed/    # Cleaned/transformed data (pipeline outputs)
├── external/     # Third-party reference data
├── cache/        # Temporary processing files
└── samples/      # Small test datasets (git-tracked)
```

### When to Use File Storage vs Database

| Use Case | Storage |
|----------|---------|
| Real-time queries | PostgreSQL/TimescaleDB |
| Historical analysis | Parquet files + DuckDB |
| ML training data | Parquet files |
| Reference lookups | PostgreSQL or JSON files |
| Temporary processing | `data/cache/` |
| Test fixtures | `data/samples/` |

### File Formats

| Format | Best For | Compression |
|--------|----------|-------------|
| Parquet | Time series, columnar data | Built-in (snappy/zstd) |
| CSV | Small datasets, human-readable | None |
| JSON | Configuration, metadata | None |
| Feather | Fast pandas I/O | Built-in |

**Recommendation:** Use Parquet for all analytical data.

### Naming Convention

For time-series data:
```
{source}_{asset}_{timeframe}_{start}_{end}.parquet

Examples:
- binance_btcusdt_1h_20230101_20231231.parquet
- yahoo_spy_1d_20200101_20231231.parquet
```

### Git Strategy

| Directory | Git Tracked | Reason |
|-----------|-------------|--------|
| `raw/` | No | Too large, can be re-downloaded |
| `processed/` | No | Can be regenerated from raw |
| `external/` | No | Third-party, usually large |
| `cache/` | No | Temporary, safe to delete |
| `samples/` | Yes | Small test fixtures needed for CI |

**Size guidelines:**
- `samples/`: Keep total under 10MB
- Individual files > 100MB: Never in git
- Files 10-100MB: Consider Git LFS if versioning needed

### Large File Management

For datasets too large for git:

1. **Document download scripts** in `scripts/`
2. **Use DVC** (Data Version Control) for versioned data pipelines
3. **Use Git LFS** only for medium files that truly need versioning
4. **Cloud storage** (S3, GCS) for very large datasets with local caching

### Integration with DuckDB

Query Parquet files directly:

```python
import duckdb

# Query without loading into memory
result = duckdb.query("""
    SELECT date, close 
    FROM 'data/raw/binance_btcusdt_1h_*.parquet'
    WHERE date >= '2023-01-01'
""").df()
```

---

## ORM Usage

### Standard: SQLAlchemy 2.0

SQLAlchemy is used for database interaction.

### When to Use ORM

- CRUD operations on single entities
- Simple queries with filters
- Relationship traversal
- Model validation and serialization

### When to Use Raw SQL

- Complex joins across multiple tables
- Aggregations and GROUP BY
- Time-series queries with TimescaleDB functions
- Performance-critical queries
- Bulk operations (insert/update many rows)
- Database-specific features

### Query Patterns

- Use async session for all database operations
- Explicit transaction boundaries
- Connection pooling with appropriate limits
- Query timeout enforcement

---

## Schema Management

### Migrations: Alembic

All schema changes go through Alembic migrations.

Requirements:
- Every migration has upgrade and downgrade scripts
- Migrations are idempotent where possible
- Migrations include data transformations when needed
- Migrations are tested before deployment

### Migration Naming

Format: `YYYYMMDD_HHMMSS_description.py`

Description is lowercase with underscores, describes the change.

### Breaking Changes

Schema changes that break existing code require:
1. Migration that supports both old and new
2. Code deployment
3. Migration that removes old schema

Never deploy schema changes and code changes simultaneously.

---

## Data Consistency

### Transaction Boundaries

- Single entity operations: Single transaction
- Multi-entity business operations: Single transaction
- Cross-service operations: Saga pattern with compensation

### Isolation Levels

Default: READ COMMITTED

Use SERIALIZABLE only when business logic requires (rare).

### Optimistic Locking

Entities with concurrent access include version columns. Updates specify expected version; conflict returns 409.

---

## Backup and Recovery

### Backup Schedule

- Full backup: Daily
- Incremental backup: Hourly
- Transaction log backup: Continuous (WAL archiving)

### Recovery Testing

Restore from backup monthly in non-production environment. Verify data integrity.

### Point-in-Time Recovery

Maintain ability to restore to any point within retention window (minimum 7 days).

---

## Adoption Checklist

When adopting this module:

- [ ] Review which optional components are needed
- [ ] Configure PostgreSQL connection pooling
- [ ] Set up Alembic migrations
- [ ] Configure Redis with appropriate memory limits
- [ ] Implement backup strategy
- [ ] Set up monitoring for database health

### Optional Components Checklist

**TimescaleDB:**
- [ ] Install TimescaleDB extension
- [ ] Create hypertables for time-series data
- [ ] Configure compression policies
- [ ] Set up continuous aggregates

**DuckDB:**
- [ ] Set up Parquet export pipeline
- [ ] Configure analysis environment
- [ ] Document query patterns

**File-Based Data Storage:**
- [ ] Create `data/` directory structure
- [ ] Configure `.gitignore` for data files
- [ ] Document data sources in `data/README.md`
- [ ] Create download/processing scripts in `scripts/`
- [ ] Set up sample data for tests in `data/samples/`
- [ ] Consider DVC if data versioning needed
