# 02 - Primitive Identification

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic primitive identification guide

---

## Purpose

Primitive Identification forces explicit declaration of the fundamental data type that flows through a system. Without this decision, systems accumulate multiple competing primitives, exponentially increasing complexity.

**Key insight**: Systems with one primitive scale linearly. Systems with multiple primitives scale quadratically in complexity.

---

## Context

The problem is complexity explosion. When a system has one core data type (an Order, a Task, a Message), every new feature is an operation on that type and the system grows linearly. When a system has three competing types (Orders, Jobs, and Requests that all represent "work"), every new feature must handle all three, and the interactions between them grow quadratically.

This decision must be made explicitly and early. Systems that skip this step don't avoid having a primitive — they end up with several unofficial ones, each created by a different developer solving a different problem. By the time the inconsistency is visible, it is embedded across the codebase and expensive to unify.

This document forces the choice upfront: identify the single fundamental data type that flows through the entire system, give it a UUID, a lifecycle with clear states, and timestamps. Every module, every API, every storage layer is then designed around this type. The constraint feels restrictive initially, but it radically simplifies everything downstream — from API design (03) to module boundaries (04) to database schemas (20).

---

## What Is A Primitive?

A primitive is the fundamental unit of data that flows through your entire system. Every module, every API, every storage layer should be designed around this single type.

### Characteristics of a Good Primitive

- **Universal**: Every operation can be expressed in terms of this type
- **Composable**: Complex operations are sequences of primitives
- **Identifiable**: Has a unique identifier (usually UUID)
- **Stateful**: Has a lifecycle with clear states
- **Timestamped**: Tracks creation and modification times

### Examples by Domain

| Domain | Primitive | Why |
|--------|-----------|-----|
| E-commerce | `Order` | All operations relate to orders |
| Task management | `Task` | Everything is a task or relates to one |
| Content platform | `Content` | Posts, comments, media are all content |
| Financial system | `Transaction` | All money movement is a transaction |
| Messaging system | `Message` | Core unit of communication |
| AI agent platform | `AgentTask` | All work flows as tasks |

---

## Primitive Template

When defining your primitive, use this template:

```
Primitive: {Name}

| Attribute | Type | Description |
|-----------|------|-------------|
| id | UUID | Unique identifier |
| type | Enum | Categorizes the primitive |
| status | Enum | Lifecycle state |
| input | JSON | Input data |
| output | JSON | Result data |
| parent_id | UUID | For hierarchies (optional) |
| context | JSON | Accumulated context |
| created_at | datetime | Creation timestamp |
| updated_at | datetime | Last update timestamp |
```

Customize attributes based on your domain, but maintain:
- Unique identification
- Status tracking
- Timestamps
- Flexible payload (JSON fields)

---

## Rules

### 1. Single Primitive Enforcement

The system processes **only** your declared primitive. Other data structures are either:

- Attributes of the primitive
- Input/output payloads
- Implementation details hidden within modules

### 2. New Features Express as Primitives

When adding features, ask:

> "How does this express as a {Primitive}?"

If it doesn't fit the primitive model, either:

- Reframe it as a primitive instance
- Reconsider if it belongs in this system

### 3. No Parallel Primitives

Do not introduce competing concepts:

- No "Jobs" that aren't primitives
- No "Requests" separate from primitives
- No "Operations" as a separate thing
- No "Workflows" as first-class entities (workflows are primitive sequences)

### 4. Composition Over New Types

Complex operations compose from primitives:

```
Workflow = [Primitive1, Primitive2, Primitive3]
Batch = [Primitive, Primitive, Primitive]
Pipeline = [Stage1Primitive, Stage2Primitive, ...]
```

---

## Implementation Checklist

When building any feature:

- [ ] Can this be expressed as the declared primitive?
- [ ] Does this create a new primitive type? (If yes, reconsider)
- [ ] Is this primitive composable with existing primitives?
- [ ] Does the primitive flow through existing infrastructure?
- [ ] Will existing tools (monitoring, history, CLI) work with this?

---

## Exceptions

Limited exceptions exist for infrastructure concerns:

| Exception | Justification |
|-----------|---------------|
| User/Auth entities | Identity is orthogonal to primitive processing |
| Configuration | System metadata, not workflow data |
| Logs/Metrics | Observability layer, not business data |

These do not participate in the primitive processing pipeline.

---

## Process: Identifying Your Primitive

### Step 1: List All Operations

Write down every operation your system performs:
- User creates project
- System processes data
- User views results
- System sends notifications

### Step 2: Find the Common Thread

What noun appears in most operations? What flows through the system end-to-end?

### Step 3: Define the Primitive

Use the template above. Include:
- All states it can be in
- All types/categories
- Input and output structures

### Step 4: Validate Against Operations

Re-examine your operation list. Can each be expressed as:
- Creating a primitive
- Updating a primitive
- Querying primitives
- Composing primitives

If not, refine your primitive definition.

### Step 5: Document and Enforce

- Add primitive definition to architecture docs
- Create database schema for primitive
- Build APIs around primitive CRUD
- Ensure all modules speak in terms of primitives

---

## Example: Task Management System

### Primitive Definition

```
Primitive: Task

| Attribute | Type | Description |
|-----------|------|-------------|
| id | UUID | Unique identifier |
| project_id | UUID | Parent project |
| type | Enum | bug, feature, chore, epic |
| status | Enum | pending, in_progress, completed, cancelled |
| title | string | Task title |
| description | text | Detailed description |
| assignee_id | UUID | Assigned user |
| input | JSON | Task requirements, acceptance criteria |
| output | JSON | Completion notes, deliverables |
| parent_task_id | UUID | For subtasks |
| created_at | datetime | Creation timestamp |
| updated_at | datetime | Last update timestamp |
```

### How Operations Map

| Operation | Primitive Expression |
|-----------|---------------------|
| Create bug report | Create Task (type=bug) |
| Assign to developer | Update Task (assignee_id) |
| Mark complete | Update Task (status=completed) |
| Create subtasks | Create Task (parent_task_id=parent) |
| View sprint | Query Tasks (project_id, status) |
| Generate report | Query Tasks (aggregate) |

---

## Anti-Patterns

### Multiple Primitives

```
# BAD: Competing primitives
class Task: ...
class Job: ...
class Request: ...
class WorkItem: ...
```

### Primitive Bypass

```
# BAD: Direct database writes bypassing primitive
def quick_update(table, data):
    db.execute(f"UPDATE {table} SET ...")
```

### Type Explosion

```
# BAD: New class for every variation
class BugTask: ...
class FeatureTask: ...
class ChoreTask: ...

# GOOD: Single primitive with type field
class Task:
    type: Enum[bug, feature, chore]
```

---

## Integration with Architecture Layers

Once you've identified your primitive, it flows through the backend architecture layers (doc 03) as follows:

```
1. Model      → SQLAlchemy model with primitive fields (id, type, status, timestamps)
2. Repository → CRUD operations on the primitive's table
3. Service    → Business logic that transitions primitive states
4. Schema     → Pydantic schemas for API request/response shapes
5. API        → HTTP endpoints that expose primitive operations
6. Events     → State changes publish events (e.g. task.task.created, task.task.completed)
```

### Worked Example: Task Primitive

```python
# 1. Model: modules/backend/models/task.py
class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime]

# 2. Repository: modules/backend/repositories/task_repository.py
class TaskRepository:
    async def create(self, task: Task) -> Task: ...
    async def get_by_id(self, task_id: UUID) -> Task | None: ...
    async def update_status(self, task_id: UUID, status: str) -> Task: ...

# 3. Service: modules/backend/services/task_service.py
class TaskService:
    async def create_task(self, data: CreateTaskSchema) -> TaskSchema:
        task = Task(**data.model_dump())
        task = await self.repo.create(task)
        # Publish event on state change
        await self._publish_event("tasks.task.created", {"task_id": str(task.id)})
        return TaskSchema.model_validate(task)

# 4. Schema: modules/backend/schemas/task_schema.py
class CreateTaskSchema(BaseModel):
    title: str

class TaskSchema(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime

# 5. API: modules/backend/api/v1/endpoints/tasks.py
@router.post("/tasks", response_model=TaskSchema)
async def create_task(data: CreateTaskSchema, db: DbSession):
    service = TaskService(db)
    return await service.create_task(data)
```

Every domain entity in the project follows this exact flow. The primitive is the entity that appears at every layer.

---

## Reference

Based on Eskil Steenberg's Primitive Identification principle.

Key insight: Complexity scales with the square of the number of primitives. One primitive = linear complexity. Two primitives = quadratic complexity. Keep it to one.
