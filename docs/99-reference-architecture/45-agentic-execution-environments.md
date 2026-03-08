# 45 — Execution Environments (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-03-05*

## Changelog

- 1.0.0 (2026-03-05): Initial execution environments standard — container lifecycle management, three execution modes (local/container/sandbox), Docker runtime integration, network isolation, volume persistence, cloud deployment patterns, Temporal Activity integration, security hardening, testing

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Has agents that need physical isolation beyond filesystem scope (doc 47 Dimension 4)
- Runs playbook steps (doc 16) that declare `environment: container` or `environment: sandbox`
- Needs agents to install packages, run arbitrary scripts, or access the network without risking the host
- Operates long-running agent workspaces that persist state across scheduled executions (daily scraping, threat intelligence gathering, data pipelines)
- Requires defense-in-depth isolation for agent-generated or agent-executed code

**Dependencies**: This module requires **03-backend-architecture.md** (service layer), **47-agentic-module-organization.md** (execution mode field in agent YAML), and **14-background-tasks.md** (task execution). It benefits from **40-agentic-architecture.md** (orchestration patterns) and **46-agentic-event-session-architecture.md** (Tier 4 Temporal integration).

**Relationship to other modules**: This module implements the `environment` field that doc 47 defines and Plan 16 consumes. It does not replace any existing module. It adds a service (`ExecutionEnvironmentService`) that the coordinator and Temporal Activities call when a task's execution environment is not `local`.

| Module | Role | Changed by this doc |
|--------|------|---------------------|
| **47** (Agent Module Organization) | Defines `execution.mode: local \| container` in agent YAML | ❌ Unchanged — this doc implements what 47 defines |
| **Plan 16** (Playbooks & Missions) | Stores `_execution_environment` in plan task metadata | ❌ Unchanged — this doc reads that metadata |
| **40/41** (Agentic Architecture / PydanticAI) | Agent orchestration and delegation | ❌ Unchanged — agents don't know they run in containers |
| **46** (Event-Driven Sessions) | Tier 4 Temporal Activities execute tasks | ✅ Activities gain container awareness via this module |
| **06** (Security Standards) | Defense-in-depth, resource limits | ❌ Unchanged — this doc extends 06 at the infrastructure level |
| **14** (Background Tasks) | Taskiq worker processes | ❌ Unchanged — Taskiq workers invoke the environment service |
| **15** (Deployment: Bare Metal) | systemd services, no containers | ✅ Adds Docker runtime as a managed dependency |

---

## Context

The platform's security model enforces agent isolation at two levels: logical isolation via filesystem scope (doc 47, Dimension 3) and physical isolation via execution mode (doc 47, Dimension 4). Logical isolation works when agents operate within the platform process — a `FileScope` check before every read/write prevents agents from accessing paths outside their configuration. This covers most platform agents (QA, health monitoring, code review) that read local files and call LLMs.

Physical isolation is required when agents perform actions that logical isolation cannot constrain: installing packages, executing downloaded scripts, scraping websites with headless browsers, running test suites that spawn child processes, or maintaining long-lived environments with cached state between scheduled executions. In these cases, the agent's task must execute inside a container with its own filesystem, network namespace, process tree, and resource limits — so that a compromised or misbehaving agent cannot affect the host, other agents, or the platform itself.

The challenge is that these containers must be **managed by the platform**, not by the agents. Agents do not know they run in containers. The coordinator resolves the execution environment from the task metadata (set by the agent YAML or the playbook step), calls the `ExecutionEnvironmentService` to provision or reuse a container, executes the task inside it, captures output, and returns results to the platform's normal data flow. From the agent's perspective, it called a tool and got a result. From the platform's perspective, that tool invocation happened in an isolated environment with explicit resource and network constraints.

This module defines the container lifecycle, runtime configuration, security hardening, volume management, network policy, and cloud deployment patterns that make this work. The container runtime is Docker, managed programmatically via the Docker SDK for Python (`docker-py`). Docker was chosen because it has the best Python API of any container runtime, runs natively on both macOS (via OrbStack, Colima, or Docker Desktop) and Linux, uses the same images locally and in cloud (ECS, Kubernetes, Fly.io), and is the universal standard that every deployment target supports. This is not a Kubernetes architecture — it is a Docker architecture that can deploy to Kubernetes when the scale justifies it.

---

## Architecture

```
                        Platform Process (FastAPI + Workers)
                        ────────────────────────────────────
    ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
    │   Coordinator   │  │ Temporal Worker  │  │  Taskiq Worker   │
    │  (routes tasks) │  │  (Tier 4 plans) │  │  (background)    │
    └────────┬────────┘  └────────┬────────┘  └────────┬─────────┘
             │                    │                     │
             │ task.environment   │ activity input      │ task metadata
             │ != "local"        │ has _execution_env  │ has _execution_env
             │                    │                     │
             ▼                    ▼                     ▼
    ┌────────────────────────────────────────────────────────────┐
    │              ExecutionEnvironmentService                    │
    │                                                            │
    │  resolve_or_create(env_config) → EnvironmentHandle         │
    │  execute_in_environment(handle, task) → TaskResult          │
    │  health_check(handle) → HealthStatus                       │
    │  archive(handle) → snapshot saved                           │
    │  destroy(handle) → resources freed                          │
    │                                                            │
    │  Manages: lifecycle, resource limits, volume mounts,       │
    │           network policy, health monitoring, image builds   │
    └──────────────────────────┬─────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
    ┌───────────────────────┐  ┌───────────────────────┐
    │   ContainerBackend    │  │   ContainerBackend     │
    │   (docker-py)         │  │   (cloud — future)     │
    │                       │  │                        │
    │  Docker Engine        │  │  ECS Fargate / K8s     │
    │  (local or remote)    │  │  (via boto3 / k8s-py)  │
    └───────────┬───────────┘  └───────────┬────────────┘
                │                          │
                ▼                          ▼
    ┌───────────────────────┐  ┌───────────────────────┐
    │  Container Instance   │  │  Container Instance    │
    │                       │  │                        │
    │  Named volumes for    │  │  EFS/PV for            │
    │  persistent data      │  │  persistent data       │
    │                       │  │                        │
    │  Network: restricted  │  │  Network: VPC + SG     │
    │  egress allowlist     │  │  egress allowlist      │
    └───────────────────────┘  └───────────────────────┘
```

**Key architectural decisions:**

1. **Agents do not know about containers.** The execution environment is resolved by infrastructure (coordinator, Temporal Activity, Taskiq worker), never by the agent itself. An agent's tool function executes identically regardless of whether it runs in-process or in a container.

2. **The platform process is never containerized by this module.** FastAPI, Redis, PostgreSQL, Temporal, and Taskiq workers run on the host (bare metal per doc 15 or cloud VMs per doc 16). Only agent task execution runs in containers. The control plane is bare-metal; the data plane is containerized.

3. **Containers are managed, not orchestrated.** This is not Kubernetes. There is no scheduler, no service mesh, no ingress controller. A Python service (`ExecutionEnvironmentService`) calls `docker-py` to create, start, exec, stop, and remove containers. The complexity lives in lifecycle management, not in orchestration.

4. **Long-lived containers are first-class.** Unlike ephemeral sandboxes that spin up per-task, agent environments can persist across scheduled executions. A daily threat intelligence container retains its cached sessions, downloaded packages, and working state between runs. The lifecycle model supports this explicitly.

---

## Execution Modes

Three modes, matching the values declared in agent YAML (doc 47) and playbook steps (Plan 16):

| Mode | Where task runs | Isolation | Persistence | When to use |
|------|----------------|-----------|-------------|-------------|
| `local` | In the platform process | Logical (FileScope) | N/A — uses platform filesystem | Default. LLM calls, file analysis, code review, any task that doesn't need network access or package installation |
| `container` | In a Docker container on the same host | Physical (container boundary) | Named volumes survive container restarts | Web scraping, package installation, test execution, build pipelines, long-lived agent workspaces |
| `sandbox` | In a hardened Docker container with gVisor runtime | Physical (user-space kernel) | Named volumes, but no host filesystem access | Executing untrusted code, processing untrusted input, running third-party scripts, any task where container escape is a credible threat |

**`local` is the default.** The `container` and `sandbox` modes are opt-in per agent or per playbook step. If an agent's YAML does not specify `execution.mode`, it runs `local`. If a playbook step does not specify `environment`, it runs `local`.

**`sandbox` requires gVisor.** The `sandbox` mode uses Docker's `--runtime=runsc` flag, which requires gVisor to be installed on the host. gVisor intercepts all system calls in a user-space kernel, preventing container escape exploits that bypass the shared Linux kernel. On macOS, gVisor runs inside Docker's Linux VM transparently. On Linux, it runs natively. If gVisor is not installed and a task requests `sandbox` mode, the service fails the task immediately (P5: Fail Fast) with a clear error message — it does not silently downgrade to `container`.

---

## Container Lifecycle

### States

```
                                   ┌─────────────┐
                      create()     │             │
              ┌───────────────────→│   CREATED   │
              │                    │             │
              │                    └──────┬──────┘
              │                           │ start()
              │                           ▼
              │                    ┌─────────────┐
              │                    │             │    health_check()
              │                    │   RUNNING   │◄────────────────┐
              │                    │             │─────────────────┘
              │                    └──────┬──────┘
              │                           │
              │              ┌────────────┼────────────┐
              │              │            │            │
              │         stop()      archive()    crash/OOM
              │              │            │            │
              │              ▼            ▼            ▼
              │       ┌──────────┐ ┌──────────┐ ┌──────────┐
              │       │ STOPPED  │ │ ARCHIVED │ │  FAILED  │
              │       └──────┬───┘ └──────┬───┘ └──────┬───┘
              │              │            │            │
              │         start()      restore()    destroy()
              │              │            │            │
              │              ▼            ▼            ▼
              │         RUNNING      RUNNING      DESTROYED
              │
         resolve_or_create()
         (checks for existing)
```

| State | Description | Billing (cloud) |
|-------|-------------|-----------------|
| `CREATED` | Container exists but is not running. Image pulled, volumes mounted. | Storage only |
| `RUNNING` | Container is executing. Tasks can be submitted via `exec`. | Compute + storage |
| `STOPPED` | Container halted gracefully. Filesystem preserved. Can restart. | Storage only |
| `ARCHIVED` | Container committed to an image snapshot. Original container removed. Volumes preserved. | Image storage + volume storage |
| `FAILED` | Container exited unexpectedly (crash, OOM, timeout). Logs captured. | Stopped billing |
| `DESTROYED` | Container and ephemeral storage removed. Named volumes optionally retained. | None (volumes if retained) |

### Lifecycle Management

Every container is tracked in PostgreSQL via the `execution_environments` table:

```python
# modules/backend/models/execution_environment.py
import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Float, JSON, Enum as SAEnum, Index
from sqlalchemy.dialects.postgresql import UUID
from modules.backend.models.base import Base
from modules.backend.core.utils import utc_now


class EnvironmentStatus(str, enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    ARCHIVED = "archived"
    FAILED = "failed"
    DESTROYED = "destroyed"


class EnvironmentMode(str, enum.Enum):
    CONTAINER = "container"
    SANDBOX = "sandbox"


class ExecutionEnvironment(Base):
    __tablename__ = "execution_environments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(SAEnum(EnvironmentStatus), nullable=False, default=EnvironmentStatus.CREATED)

    # Identity
    name = Column(String(200), nullable=False, unique=True)     # e.g., "threat-intel-daily-scraper"
    mode = Column(SAEnum(EnvironmentMode), nullable=False)
    owner_agent = Column(String(100), nullable=True)            # Agent that owns this environment
    owner_playbook = Column(String(100), nullable=True)         # Playbook that owns this environment

    # Container reference
    container_id = Column(String(64), nullable=True)            # Docker container ID (short hash)
    image = Column(String(500), nullable=False)                 # Docker image used
    image_digest = Column(String(100), nullable=True)           # Image digest for reproducibility

    # Resource configuration (from environment template)
    cpu_limit = Column(Float, nullable=False, default=1.0)      # CPU cores
    memory_limit_mb = Column(Integer, nullable=False, default=512)
    disk_limit_mb = Column(Integer, nullable=True)
    network_policy = Column(JSON, nullable=False, default=dict)  # Egress allowlist

    # Runtime state
    last_task_at = Column(DateTime, nullable=True)
    task_count = Column(Integer, nullable=False, default=0)
    total_cpu_seconds = Column(Float, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    last_error = Column(String(2000), nullable=True)

    # Lifecycle configuration
    auto_stop_after_seconds = Column(Integer, nullable=True)     # Auto-stop after idle period
    auto_archive_after_seconds = Column(Integer, nullable=True)  # Archive after stopped period
    auto_destroy_after_seconds = Column(Integer, nullable=True)  # Destroy after archived period
    max_lifetime_seconds = Column(Integer, nullable=True)        # Hard cap on total lifetime

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=utc_now)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_exec_env_status", "status"),
        Index("ix_exec_env_owner_agent", "owner_agent"),
        Index("ix_exec_env_owner_playbook", "owner_playbook"),
    )
```

**Why PostgreSQL and not just Docker state?** Because `docker ps` is a point-in-time snapshot of one host. The platform needs to query environments across restarts, track usage metrics, enforce lifecycle policies via scheduled tasks, and audit who created what and when. Docker is the runtime; PostgreSQL is the record of truth (P3: Single Source of Truth).

---

## ExecutionEnvironmentService

The service layer that all callers use. No caller interacts with Docker directly.

```python
# modules/backend/services/execution_environment.py
from modules.backend.core.logging import get_logger
from modules.backend.core.config import get_app_config
from modules.backend.repositories.execution_environment import ExecutionEnvironmentRepository
from modules.backend.services.container_backend import ContainerBackend

logger = get_logger(__name__)


class ExecutionEnvironmentService:
    """Manages isolated execution environments for agent tasks.

    This service is the single entry point for container lifecycle management.
    The coordinator, Temporal Activities, and Taskiq workers call this service
    when a task's execution environment is not 'local'.

    The service does not contain business logic about what agents do — it
    manages where they do it. Same rule as all services (doc 03).
    """

    def __init__(
        self,
        repository: ExecutionEnvironmentRepository,
        backend: ContainerBackend,
    ) -> None:
        self._repo = repository
        self._backend = backend
        self._config = get_app_config().execution_environments

    async def resolve_or_create(
        self,
        environment_name: str,
        template_name: str,
        mode: str = "container",
    ) -> EnvironmentHandle:
        """Find an existing environment or create one from a template.

        If an environment with this name exists and is RUNNING or STOPPED,
        reuse it. If STOPPED, start it. If ARCHIVED, restore it.
        If no environment exists, create one from the named template.

        This is the primary entry point. Callers provide a logical name
        (e.g., 'threat-intel-daily-scraper') and a template
        (e.g., 'scraper-python'). The service handles everything else.
        """
        existing = await self._repo.find_by_name(environment_name)

        if existing and existing.status == EnvironmentStatus.RUNNING:
            logger.info("Reusing running environment", extra={
                "environment": environment_name,
                "container_id": existing.container_id,
            })
            return EnvironmentHandle(record=existing, backend=self._backend)

        if existing and existing.status == EnvironmentStatus.STOPPED:
            logger.info("Restarting stopped environment", extra={
                "environment": environment_name,
            })
            await self._backend.start(existing.container_id)
            existing.status = EnvironmentStatus.RUNNING
            existing.started_at = utc_now()
            await self._repo.update(existing)
            return EnvironmentHandle(record=existing, backend=self._backend)

        if existing and existing.status == EnvironmentStatus.ARCHIVED:
            logger.info("Restoring archived environment", extra={
                "environment": environment_name,
            })
            return await self._restore_archived(existing, template_name)

        # No usable environment exists — create from template
        template = self._config.templates[template_name]
        return await self._create_from_template(
            environment_name, template, mode,
        )

    async def execute_in_environment(
        self,
        handle: EnvironmentHandle,
        command: list[str],
        working_dir: str = "/workspace",
        timeout_seconds: int = 300,
        env_vars: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Execute a command inside the environment.

        Returns stdout, stderr, exit code, and execution metrics.
        The environment must be RUNNING.

        This is a blocking call — it waits for the command to complete
        or timeout. For long-running commands, use execute_detached()
        and poll with get_status().
        """
        record = handle.record
        if record.status != EnvironmentStatus.RUNNING:
            raise EnvironmentNotRunningError(
                f"Environment '{record.name}' is {record.status.value}, not running"
            )

        result = await self._backend.exec_run(
            container_id=record.container_id,
            command=command,
            working_dir=working_dir,
            timeout_seconds=timeout_seconds,
            env_vars=env_vars or {},
        )

        # Update metrics
        record.last_task_at = utc_now()
        record.task_count += 1
        record.total_cpu_seconds += result.cpu_seconds
        if result.exit_code != 0:
            record.error_count += 1
            record.last_error = result.stderr[:2000] if result.stderr else None
        await self._repo.update(record)

        return result

    async def health_check(self, handle: EnvironmentHandle) -> HealthStatus:
        """Check if the environment is healthy and responsive."""
        ...

    async def stop(self, handle: EnvironmentHandle) -> None:
        """Gracefully stop the environment. Preserves filesystem."""
        ...

    async def archive(self, handle: EnvironmentHandle) -> str:
        """Commit container state to an image snapshot, remove container."""
        ...

    async def destroy(self, handle: EnvironmentHandle, keep_volumes: bool = False) -> None:
        """Remove the container and optionally its volumes."""
        ...

    async def run_lifecycle_maintenance(self) -> MaintenanceReport:
        """Scheduled task: enforce auto-stop, auto-archive, auto-destroy policies.

        Called by Taskiq scheduled task (doc 14). Queries all environments
        and applies lifecycle policies based on idle time and age.
        """
        ...
```

**The service follows the same layering rules as all services (doc 03).** It receives a repository and a backend via dependency injection. It does not import Docker directly — it calls `ContainerBackend`, which is the abstraction layer over the container runtime.

---

## ContainerBackend

The abstraction over the container runtime. The default implementation uses `docker-py`. Future implementations can wrap `boto3` (ECS), `kubernetes` (K8s), or Fly.io's REST API.

```python
# modules/backend/services/container_backend.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    cpu_seconds: float
    memory_peak_mb: float


@dataclass
class HealthStatus:
    healthy: bool
    cpu_percent: float
    memory_mb: float
    disk_used_mb: float
    uptime_seconds: float


class ContainerBackend(ABC):
    """Abstract interface for container runtimes.

    Implementations:
    - DockerBackend: docker-py (local and remote Docker Engine)
    - ECSBackend: boto3 (AWS Fargate — future)
    - K8sBackend: kubernetes-py (Kubernetes Pods — future)
    """

    @abstractmethod
    async def create(
        self,
        image: str,
        name: str,
        volumes: dict[str, dict],
        network_config: dict,
        resource_limits: dict,
        runtime: str = "runc",         # "runc" for container, "runsc" for sandbox
        env_vars: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
    ) -> str:
        """Create a container. Returns container ID."""
        ...

    @abstractmethod
    async def start(self, container_id: str) -> None:
        """Start a created or stopped container."""
        ...

    @abstractmethod
    async def exec_run(
        self,
        container_id: str,
        command: list[str],
        working_dir: str,
        timeout_seconds: int,
        env_vars: dict[str, str],
    ) -> ExecutionResult:
        """Execute a command inside a running container."""
        ...

    @abstractmethod
    async def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop a running container gracefully."""
        ...

    @abstractmethod
    async def remove(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        ...

    @abstractmethod
    async def commit(self, container_id: str, repository: str, tag: str) -> str:
        """Commit container state to an image. Returns image ID."""
        ...

    @abstractmethod
    async def stats(self, container_id: str) -> HealthStatus:
        """Get container resource usage stats."""
        ...

    @abstractmethod
    async def logs(self, container_id: str, tail: int = 100) -> str:
        """Get container logs."""
        ...
```

### DockerBackend Implementation

```python
# modules/backend/services/docker_backend.py
import asyncio
import docker
from docker.errors import NotFound, APIError
from modules.backend.core.logging import get_logger
from modules.backend.core.config import get_app_config
from modules.backend.services.container_backend import (
    ContainerBackend, ExecutionResult, HealthStatus,
)

logger = get_logger(__name__)


class DockerBackend(ContainerBackend):
    """Docker runtime backend using docker-py.

    Connects to the Docker daemon via the standard socket.
    On macOS (OrbStack/Colima/Docker Desktop): /var/run/docker.sock
    On Linux: /var/run/docker.sock
    Remote Docker: tcp://host:2376 with TLS

    docker-py operations are synchronous. This backend wraps them in
    asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(self) -> None:
        config = get_app_config().execution_environments.docker
        if config.host:
            self._client = docker.DockerClient(
                base_url=config.host,
                tls=config.tls_enabled,
            )
        else:
            self._client = docker.from_env()

    async def create(
        self,
        image: str,
        name: str,
        volumes: dict[str, dict],
        network_config: dict,
        resource_limits: dict,
        runtime: str = "runc",
        env_vars: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
    ) -> str:
        def _create():
            container = self._client.containers.create(
                image=image,
                name=name,
                volumes=volumes,
                environment=env_vars or {},
                labels={
                    "bfa.managed": "true",
                    "bfa.environment": name,
                    **(labels or {}),
                },
                runtime=runtime,
                detach=True,
                stdin_open=True,
                # Resource limits
                mem_limit=f"{resource_limits['memory_limit_mb']}m",
                nano_cpus=int(resource_limits['cpu_limit'] * 1e9),
                # Security
                cap_drop=["ALL"],
                cap_add=resource_limits.get("cap_add", []),
                security_opt=resource_limits.get("security_opt", []),
                # Restart policy — long-lived environments restart on failure
                restart_policy=(
                    {"Name": "on-failure", "MaximumRetryCount": 3}
                    if resource_limits.get("long_lived", False)
                    else {"Name": "no"}
                ),
                # Network
                network=network_config.get("network_name", "bfa-agent-net"),
            )
            return container.short_id

        return await asyncio.to_thread(_create)

    async def exec_run(
        self,
        container_id: str,
        command: list[str],
        working_dir: str,
        timeout_seconds: int,
        env_vars: dict[str, str],
    ) -> ExecutionResult:
        def _exec():
            container = self._client.containers.get(container_id)
            start_time = asyncio.get_event_loop().time()

            exec_result = container.exec_run(
                cmd=command,
                workdir=working_dir,
                environment=env_vars,
                demux=True,
            )

            elapsed = asyncio.get_event_loop().time() - start_time
            stdout_bytes, stderr_bytes = exec_result.output
            return ExecutionResult(
                exit_code=exec_result.exit_code,
                stdout=(stdout_bytes or b"").decode("utf-8", errors="replace"),
                stderr=(stderr_bytes or b"").decode("utf-8", errors="replace"),
                duration_seconds=elapsed,
                cpu_seconds=elapsed,     # Approximation; precise via stats API
                memory_peak_mb=0,        # Requires stats snapshot
            )

        return await asyncio.to_thread(_exec)

    async def start(self, container_id: str) -> None:
        await asyncio.to_thread(
            lambda: self._client.containers.get(container_id).start()
        )

    async def stop(self, container_id: str, timeout: int = 10) -> None:
        await asyncio.to_thread(
            lambda: self._client.containers.get(container_id).stop(timeout=timeout)
        )

    async def remove(self, container_id: str, force: bool = False) -> None:
        await asyncio.to_thread(
            lambda: self._client.containers.get(container_id).remove(force=force)
        )

    async def commit(self, container_id: str, repository: str, tag: str) -> str:
        def _commit():
            container = self._client.containers.get(container_id)
            image = container.commit(repository=repository, tag=tag)
            return image.short_id

        return await asyncio.to_thread(_commit)

    async def stats(self, container_id: str) -> HealthStatus:
        def _stats():
            container = self._client.containers.get(container_id)
            raw = container.stats(stream=False)
            # Parse Docker stats response
            cpu_delta = raw["cpu_stats"]["cpu_usage"]["total_usage"] - \
                raw["precpu_stats"]["cpu_usage"]["total_usage"]
            system_delta = raw["cpu_stats"]["system_cpu_usage"] - \
                raw["precpu_stats"]["system_cpu_usage"]
            cpu_percent = (cpu_delta / system_delta * 100) if system_delta > 0 else 0
            memory_mb = raw["memory_stats"].get("usage", 0) / (1024 * 1024)

            return HealthStatus(
                healthy=container.status == "running",
                cpu_percent=round(cpu_percent, 2),
                memory_mb=round(memory_mb, 1),
                disk_used_mb=0,
                uptime_seconds=0,
            )

        return await asyncio.to_thread(_stats)

    async def logs(self, container_id: str, tail: int = 100) -> str:
        def _logs():
            container = self._client.containers.get(container_id)
            return container.logs(tail=tail).decode("utf-8", errors="replace")

        return await asyncio.to_thread(_logs)
```

**`asyncio.to_thread()` wraps all Docker calls.** The `docker-py` library is synchronous. Blocking the FastAPI event loop would stall all concurrent requests. Every Docker operation runs in a thread pool. This is the same pattern used for synchronous database drivers.

---

## Environment Templates

Templates define the container image, resource limits, volume mounts, network policy, and lifecycle settings for a class of environments. They live in YAML configuration (P4: Scope Is Configuration, Not Code).

### Configuration

```yaml
# config/settings/environments.yaml
# =============================================================================
# Execution Environment Configuration
# =============================================================================
# Defines templates for containerized agent execution environments.
# Templates are referenced by agent YAML (execution.template) and
# playbook steps (environment_template).
#
# All values have secure defaults. Empty egress_allowlist = deny all (P8).
# =============================================================================

execution_environments:
  enabled: false                        # Feature flag — disabled until Docker is available

  docker:
    host: null                          # null = use default socket. Set for remote Docker.
    tls_enabled: false
    network_name: "bfa-agent-net"       # Custom bridge network for agent containers
    label_prefix: "bfa"                 # Labels applied to all managed containers

  # Image registry for pre-built environment images
  registry:
    prefix: "bfa-env"                   # Image naming: bfa-env/scraper-python:latest
    build_context: "config/environments/dockerfiles"

  # Global resource defaults (templates can override)
  defaults:
    cpu_limit: 1.0                      # CPU cores
    memory_limit_mb: 512
    disk_limit_mb: 2048
    timeout_seconds: 300                # Default task execution timeout
    auto_stop_after_seconds: 3600       # Stop idle containers after 1 hour
    auto_archive_after_seconds: 86400   # Archive stopped containers after 24 hours
    auto_destroy_after_seconds: 604800  # Destroy archived environments after 7 days
    max_lifetime_seconds: 2592000       # Hard cap: 30 days

  # Environment templates
  templates:
    scraper-python:
      description: "Python environment with web scraping capabilities"
      dockerfile: "scraper-python.Dockerfile"
      cpu_limit: 2.0
      memory_limit_mb: 1024
      disk_limit_mb: 4096
      long_lived: true                  # Restart on failure, persist across runs
      auto_stop_after_seconds: 7200     # 2 hours idle
      volumes:
        workspace:
          mount: "/workspace"
          persist: true                 # Named volume, survives container restarts
        cache:
          mount: "/cache"
          persist: true                 # Cached scraped data survives between runs
        output:
          mount: "/output"
          persist: false                # Ephemeral, cleared each run
      network:
        egress_allowlist:               # Only these domains reachable (P8)
          - "*.github.com"
          - "*.githubusercontent.com"
          - "api.openai.com"
          - "api.anthropic.com"
          - "simonwillison.net"
          - "karpathy.ai"
          # Add domains per playbook — see "Network Policy" section
        egress_deny:                    # Explicit denials (override allowlist wildcards)
          - "metadata.google.internal"
          - "169.254.169.254"           # AWS IMDS
        dns: "1.1.1.1"                 # Explicit DNS to prevent DNS rebinding

    code-runner:
      description: "Python environment for code execution and testing"
      dockerfile: "code-runner.Dockerfile"
      cpu_limit: 2.0
      memory_limit_mb: 2048
      long_lived: false                 # Ephemeral — destroyed after task
      auto_stop_after_seconds: 600
      auto_destroy_after_seconds: 3600
      volumes:
        workspace:
          mount: "/workspace"
          persist: false
      network:
        egress_allowlist:
          - "pypi.org"
          - "files.pythonhosted.org"

    headless-browser:
      description: "Chromium environment for browser-based scraping"
      dockerfile: "headless-browser.Dockerfile"
      cpu_limit: 2.0
      memory_limit_mb: 2048
      disk_limit_mb: 4096
      long_lived: true
      volumes:
        workspace:
          mount: "/workspace"
          persist: true
        browser-cache:
          mount: "/home/chrome/.cache"
          persist: true
      network:
        egress_allowlist: []            # Empty = deny all. Override per playbook step.
      security:
        cap_add:
          - "SYS_ADMIN"                # Required for Chromium sandbox
        security_opt:
          - "seccomp=chrome.json"       # Chromium-specific seccomp profile
```

### Dockerfiles

```dockerfile
# config/environments/dockerfiles/scraper-python.Dockerfile
# =============================================================================
# Scraper Python Environment
# Base image for web scraping agent workspaces.
# Pre-installs common scraping libraries. Agents can install additional
# packages at runtime via pip (within the container).
# =============================================================================
FROM python:3.12-slim

# Security: non-root user
RUN groupadd -r agent && useradd -r -g agent -m -s /bin/bash agent

# System dependencies for common scraping libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Pre-installed Python packages
RUN pip install --no-cache-dir \
    httpx \
    beautifulsoup4 \
    lxml \
    feedparser \
    trafilatura \
    newspaper3k \
    pyyaml \
    structlog

# Working directories
RUN mkdir -p /workspace /cache /output && \
    chown -R agent:agent /workspace /cache /output

USER agent
WORKDIR /workspace

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "print('ok')" || exit 1
```

### Agent YAML Integration

The `execution` block in agent YAML (doc 47) gains a `template` field:

```yaml
# config/agents/research/scraper/agent.yaml
agent_name: research.scraper.agent
agent_type: vertical
description: "Scrapes web sources, RSS feeds, and blogs for content"
enabled: true
model: google-gla:gemini-2.5-flash
max_budget_usd: 0.50

tools:
  - web.fetch_url
  - web.parse_rss
  - web.extract_article
  - filesystem.write_file
  - filesystem.read_file

scope:
  read:
    - /workspace
    - /cache
  write:
    - /workspace
    - /output

execution:
  mode: container
  template: scraper-python                # References config/settings/environments.yaml
  environment_name_pattern: "{agent_name}-{session_id}"   # Unique per session
  # Or for long-lived shared environments:
  # environment_name_pattern: "{agent_name}-shared"        # One environment, reused
```

### Playbook Step Integration

Playbook steps reference templates via the `environment_template` field:

```yaml
# In a playbook YAML file (Plan 16)
steps:
  - id: scrape
    description: "Fetch content from curated source list"
    capability: research.scraper
    environment: container
    environment_template: scraper-python   # Overrides agent default if set
    environment_name: "threat-intel-scraper"  # Long-lived, reused across runs
    input:
      sources: "@context.sources"
    output: raw_articles
    timeout_seconds: 600
```

The resolution order when the coordinator encounters a task with `environment != local`:

1. Playbook step `environment_template` (if present)
2. Agent YAML `execution.template` (if present)
3. Fail with `EnvironmentTemplateNotFoundError` (P5: Fail Fast)

---

## Network Policy

Network isolation is the single most important security control for agent containers. A container with unrestricted egress can exfiltrate data, access cloud metadata endpoints, scan internal networks, or call unauthorized APIs. All containers start with **deny-all egress** (P8: Secure by Default). Allowed destinations are explicitly listed in the environment template.

### Implementation

Network policy is enforced at two levels:

**Level 1: Docker network isolation.** All agent containers connect to a dedicated bridge network (`bfa-agent-net`). This network has no access to the host network or the Docker bridge. Inter-container communication is disabled by default (`--icc=false` on the network). The platform process connects to this network only for `exec` commands — it does not expose ports.

**Level 2: iptables egress rules.** The `ExecutionEnvironmentService` configures iptables rules inside the container (or on the host via Docker's network configuration) to restrict outbound connections to the domains in `egress_allowlist`. The implementation resolves domain names to IP addresses at container creation time and refreshes periodically.

```python
# modules/backend/services/network_policy.py
async def apply_egress_policy(
    backend: ContainerBackend,
    container_id: str,
    policy: NetworkPolicy,
) -> None:
    """Apply egress allowlist to a running container.

    Resolves domain names to IP addresses, installs iptables rules
    that block all outbound traffic except to allowed destinations.

    Called after container.start(), before any task execution.
    """
    if not policy.egress_allowlist:
        # Empty allowlist = deny all egress (P8)
        await backend.exec_run(
            container_id=container_id,
            command=[
                "iptables", "-A", "OUTPUT", "-m", "state",
                "--state", "ESTABLISHED,RELATED", "-j", "ACCEPT",
            ],
            working_dir="/",
            timeout_seconds=10,
            env_vars={},
        )
        await backend.exec_run(
            container_id=container_id,
            command=["iptables", "-A", "OUTPUT", "-j", "DROP"],
            working_dir="/",
            timeout_seconds=10,
            env_vars={},
        )
        return

    # Allow DNS (required for resolution)
    # Allow established connections (required for response packets)
    # Allow each allowlisted domain
    # Deny everything else
    # Block cloud metadata endpoints unconditionally
    ...
```

### Cloud Metadata Protection

Containers MUST NOT access cloud metadata endpoints. These endpoints (`169.254.169.254` on AWS/GCP, `metadata.google.internal` on GCP, `169.254.169.254` on Azure) expose instance credentials, service account tokens, and infrastructure secrets. A compromised agent with metadata access can escalate to full cloud account access.

This is enforced both in iptables rules and in the Docker daemon configuration (`--default-address-pool` to exclude link-local ranges).

### Per-Playbook Network Overrides

Playbooks can extend (but not bypass) the template's egress allowlist:

```yaml
# In a playbook step
steps:
  - id: scrape-threat-feeds
    capability: research.scraper
    environment: container
    environment_template: scraper-python
    network_extend:                       # ADDED to template allowlist, never replaces
      egress_allowlist:
        - "feeds.ncsc.gov.uk"
        - "www.cisa.gov"
        - "otx.alienvault.com"
```

The `network_extend` key is additive only. A playbook cannot remove entries from the template's deny list or override the cloud metadata protection. This is enforced in `ExecutionEnvironmentService.resolve_or_create()`.

---

## Temporal Activity Integration

For Tier 4 (long-running autonomous tasks), the `execute_task` Temporal Activity gains container awareness. This integrates with Plan 15.

```python
# modules/backend/temporal/activities.py (addition to Plan 15)
from temporalio import activity
from modules.backend.services.execution_environment import (
    ExecutionEnvironmentService, EnvironmentHandle,
)


@activity.defn
async def execute_task_in_environment(
    task_id: str,
    plan_id: str,
    execution_environment: str,
    environment_template: str,
    environment_name: str,
    command: list[str],
    timeout_seconds: int,
) -> TaskResultDTO:
    """Temporal Activity: execute a plan task in an isolated environment.

    Called by AgentPlanWorkflow (Plan 15) when a task's
    _execution_environment is 'container' or 'sandbox'.

    For 'local' tasks, the existing execute_task Activity runs
    the agent in-process. This Activity handles the isolated case.
    """
    env_service = activity.info().get_dependency(ExecutionEnvironmentService)
    plan_service = activity.info().get_dependency(PlanService)

    # Mark task as in-progress
    await plan_service.start_task(plan_id, task_id)

    try:
        # Resolve or create the environment
        handle = await env_service.resolve_or_create(
            environment_name=environment_name,
            template_name=environment_template,
            mode=execution_environment,
        )

        # Execute the command
        result = await env_service.execute_in_environment(
            handle=handle,
            command=command,
            timeout_seconds=timeout_seconds,
        )

        if result.exit_code != 0:
            await plan_service.fail_task(
                plan_id, task_id,
                error=f"Exit code {result.exit_code}: {result.stderr[:500]}",
            )
            return TaskResultDTO(
                task_id=task_id,
                success=False,
                error=result.stderr[:2000],
            )

        await plan_service.complete_task(
            plan_id, task_id,
            output_data={"stdout": result.stdout, "duration": result.duration_seconds},
        )
        return TaskResultDTO(
            task_id=task_id,
            success=True,
            output=result.stdout,
        )

    except Exception as exc:
        await plan_service.fail_task(plan_id, task_id, error=str(exc))
        raise  # Let Temporal handle retry
```

**The Activity is idempotent** (P6, P9). If it fails partway through and Temporal retries, `resolve_or_create` returns the existing environment, and `plan_service.start_task` is safe to call on an already-started task (state machine rejects the transition and the Activity checks current status).

---

## Docker Runtime on macOS and Linux

### macOS (Apple Silicon)

The Docker daemon does not run natively on macOS. A Linux VM hosts the daemon. Three options, in order of recommendation:

**OrbStack (recommended).** Native Swift application optimized for Apple Silicon. Uses Apple's Virtualization.framework with Rosetta 2 for x86 image support. Idle CPU usage under 0.1%. Dynamic memory allocation — the VM grows and shrinks based on container demand. Exposes the standard Docker socket (`/var/run/docker.sock`), so `docker-py` works without configuration. Commercial license required for teams; free for personal use.

**Colima (open-source alternative).** MIT-licensed. Uses Lima VMs with Apple's Virtualization.framework backend. Comparable performance to OrbStack for most workloads. Slightly higher idle resource usage. Start with `colima start --cpu 4 --memory 8 --arch aarch64`.

**Docker Desktop.** The default option. Heavier resource usage than OrbStack or Colima. Commercial license required for organizations with 250+ employees or $10M+ revenue.

All three expose the standard Docker socket. The `DockerBackend` implementation works identically across all three. No code changes for different runtimes.

### Linux

Docker Engine runs natively. Install the `docker-ce` package (not `docker.io` from Ubuntu repositories — the `docker-ce` package is maintained by Docker Inc and tracks upstream releases). The Docker socket is at `/var/run/docker.sock`.

For `sandbox` mode, install gVisor:

```bash
# gVisor installation (Ubuntu/Debian)
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list
sudo apt-get update && sudo apt-get install -y runsc

# Register gVisor runtime with Docker
sudo runsc install
sudo systemctl restart docker

# Verify
docker run --runtime=runsc hello-world
```

On macOS, gVisor runs inside the Docker VM transparently. OrbStack and Colima both support custom Docker runtimes.

---

## Cloud Deployment

The same container images run locally and in cloud. The deployment target changes, not the agent code.

### AWS ECS with Fargate (Recommended)

Fargate runs Docker containers without managing EC2 instances. Each agent environment becomes an ECS task. Fargate tasks have **no execution timeout** — they run until stopped, making them suitable for long-lived agent environments.

```yaml
# Deployment mapping (local → cloud):
#
# Local                          Cloud (ECS Fargate)
# ─────────────────────────────  ─────────────────────────────
# Docker Engine                  ECS cluster
# docker-py create()             ecs.run_task()
# Named volume                   EFS mount
# bfa-agent-net (bridge)         VPC subnet + Security Group
# iptables egress rules          Security Group egress rules
# Container restart policy       ECS service with desired_count=1
# docker stats                   CloudWatch Container Insights
```

The `ECSBackend` implementation of `ContainerBackend` translates the same API calls into Fargate operations. Agent code, playbooks, and environment templates remain unchanged. The backend is selected by configuration:

```yaml
# config/settings/environments.yaml (cloud override)
execution_environments:
  enabled: true
  backend: ecs                          # "docker" (default) or "ecs" or "k8s"

  ecs:
    cluster: "bfa-agents"
    subnets:
      - "subnet-abc123"
      - "subnet-def456"
    security_group: "sg-agent-envs"
    task_role_arn: "arn:aws:iam::123456789012:role/bfa-agent-task"
    execution_role_arn: "arn:aws:iam::123456789012:role/bfa-agent-execution"
    efs_filesystem_id: "fs-abc123"
    use_graviton: true                  # ARM64 Graviton instances (~20% cost savings)
    use_spot: true                      # Spot capacity for non-critical environments
```

### Kubernetes (Alternative)

For teams already running Kubernetes, agent environments map to Pods with PersistentVolumeClaims. The Kubernetes SIG `agent-sandbox` project provides purpose-built CRDs (`Sandbox`, `SandboxTemplate`, `WarmPool`) that align closely with this architecture. The `K8sBackend` implementation would use these CRDs or fall back to plain Pod management.

Local development uses k3d (K3s inside Docker) for Kubernetes-compatible testing on Apple Silicon.

---

## Security

### Defense in Depth

| Layer | Control | What it prevents |
|-------|---------|-----------------|
| **Container boundary** | Separate PID, mount, network namespace | Host filesystem access, host process visibility |
| **Non-root user** | `USER agent` in Dockerfile | Privilege escalation within container |
| **Dropped capabilities** | `cap_drop: ALL` | Kernel exploitation via capabilities |
| **gVisor (sandbox mode)** | User-space kernel intercepts all syscalls | Container escape via kernel vulnerabilities |
| **Network egress allowlist** | iptables rules per container | Data exfiltration, cloud metadata access, lateral movement |
| **Resource limits** | CPU, memory, disk caps | Resource exhaustion, denial of service |
| **Read-only root filesystem** | `--read-only` flag (optional per template) | Persistent malware, filesystem modification |
| **No Docker socket mount** | Never mount `/var/run/docker.sock` | Container breakout to Docker daemon |
| **Metadata endpoint blocking** | Block 169.254.169.254 | Cloud credential theft |

### Mandatory Security Rules

1. **Never mount the Docker socket into an agent container.** This gives the container full control over the Docker daemon — equivalent to root on the host. No exception, no override.

2. **All containers run as non-root.** The Dockerfile must include `USER agent` (or equivalent). The `DockerBackend.create()` enforces `user="agent"` regardless of Dockerfile content.

3. **Cloud metadata endpoints are blocked unconditionally.** The `169.254.169.254` IP and `metadata.google.internal` hostname are denied in every container's network policy. This is not configurable — it is hardcoded in `apply_egress_policy()`.

4. **Empty egress allowlist means deny-all** (P8). A template with `egress_allowlist: []` produces a container with no outbound network access. This is the default for new templates.

5. **Secrets are injected via environment variables, never mounted as files.** The `ExecutionEnvironmentService` reads secrets from the platform's `.env` and passes only the subset needed by the specific agent as container environment variables.

6. **Container images are pinned by digest in production.** Development uses `:latest` tags. Production uses `image@sha256:abc123...` to prevent supply chain attacks via tag mutation.

---

## Observability

All container lifecycle events and task executions are logged via the platform's standard structured logging (doc 10). Events are published to the session event bus (doc 46) when a session is active.

### Log Events

```python
# Structured log entries for execution environment operations
logger.info("environment.created", extra={
    "environment": name,
    "template": template_name,
    "mode": mode,
    "image": image,
    "container_id": container_id,
})

logger.info("environment.task.started", extra={
    "environment": name,
    "container_id": container_id,
    "command": command[:3],             # First 3 args only (avoid logging secrets)
    "timeout_seconds": timeout,
})

logger.info("environment.task.completed", extra={
    "environment": name,
    "exit_code": result.exit_code,
    "duration_seconds": result.duration_seconds,
    "cpu_seconds": result.cpu_seconds,
    "memory_peak_mb": result.memory_peak_mb,
})

logger.warning("environment.task.failed", extra={
    "environment": name,
    "exit_code": result.exit_code,
    "stderr": result.stderr[:500],      # Truncated
})

logger.info("environment.lifecycle", extra={
    "environment": name,
    "transition": f"{old_status} → {new_status}",
    "reason": reason,
})
```

### Session Events

```python
# Event types for the session event bus (doc 46)
class EnvironmentCreatedEvent(SessionEvent):
    event_type: str = "environment.created"
    environment_name: str
    mode: str
    template: str

class EnvironmentTaskCompletedEvent(SessionEvent):
    event_type: str = "environment.task.completed"
    environment_name: str
    exit_code: int
    duration_seconds: float

class EnvironmentFailedEvent(SessionEvent):
    event_type: str = "environment.failed"
    environment_name: str
    error: str
```

### Scheduled Health Monitoring

A Taskiq scheduled task (doc 14) runs periodically to check all RUNNING environments:

```python
# modules/backend/tasks/environment_maintenance.py
from modules.backend.tasks.broker import get_broker

broker = get_broker()


@broker.task(schedule=[{"cron": "*/5 * * * *"}])  # Every 5 minutes
async def check_environment_health() -> dict:
    """Check health of all running environments and enforce lifecycle policies.

    - Stops environments idle beyond auto_stop_after_seconds
    - Archives environments stopped beyond auto_archive_after_seconds
    - Destroys environments archived beyond auto_destroy_after_seconds
    - Destroys environments exceeding max_lifetime_seconds
    - Logs warnings for environments approaching resource limits
    """
    ...
```

---

## Testing

### Unit Tests

Unit tests mock the `ContainerBackend` interface. They verify that `ExecutionEnvironmentService` correctly manages lifecycle transitions, enforces policies, and handles errors.

```python
# tests/unit/services/test_execution_environment.py
import pytest
from unittest.mock import AsyncMock
from modules.backend.services.execution_environment import ExecutionEnvironmentService
from modules.backend.services.container_backend import ExecutionResult


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.create.return_value = "abc123"
    backend.exec_run.return_value = ExecutionResult(
        exit_code=0, stdout="ok", stderr="",
        duration_seconds=1.5, cpu_seconds=1.2, memory_peak_mb=64,
    )
    return backend


async def test_resolve_creates_new_environment(mock_backend, mock_repo):
    """When no environment exists, create from template."""
    mock_repo.find_by_name.return_value = None
    service = ExecutionEnvironmentService(mock_repo, mock_backend)

    handle = await service.resolve_or_create("test-env", "scraper-python")

    mock_backend.create.assert_called_once()
    assert handle.record.name == "test-env"
    assert handle.record.status == EnvironmentStatus.RUNNING


async def test_resolve_reuses_running_environment(mock_backend, mock_repo):
    """When a running environment exists, reuse it."""
    mock_repo.find_by_name.return_value = make_environment(
        name="test-env", status=EnvironmentStatus.RUNNING,
    )
    service = ExecutionEnvironmentService(mock_repo, mock_backend)

    handle = await service.resolve_or_create("test-env", "scraper-python")

    mock_backend.create.assert_not_called()
    assert handle.record.name == "test-env"


async def test_sandbox_fails_without_gvisor(mock_backend, mock_repo):
    """Requesting sandbox mode when gVisor unavailable fails immediately."""
    mock_backend.create.side_effect = docker.errors.APIError(
        "OCI runtime create failed: runtime 'runsc' not found"
    )
    mock_repo.find_by_name.return_value = None
    service = ExecutionEnvironmentService(mock_repo, mock_backend)

    with pytest.raises(GVisorNotAvailableError):
        await service.resolve_or_create("test-env", "code-runner", mode="sandbox")
```

### Integration Tests

Integration tests use real Docker via `testcontainers-python` or direct `docker-py` calls against the local Docker daemon:

```python
# tests/integration/services/test_execution_environment_docker.py
import pytest
import docker

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def docker_available():
    """Skip integration tests if Docker is not running."""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        pytest.skip("Docker daemon not available")


async def test_full_lifecycle(docker_available, db_session):
    """Create environment, execute command, stop, destroy."""
    backend = DockerBackend()
    repo = ExecutionEnvironmentRepository(db_session)
    service = ExecutionEnvironmentService(repo, backend)

    # Create
    handle = await service.resolve_or_create("integration-test", "code-runner")
    assert handle.record.status == EnvironmentStatus.RUNNING

    # Execute
    result = await service.execute_in_environment(
        handle, command=["python", "-c", "print('hello')"],
    )
    assert result.exit_code == 0
    assert "hello" in result.stdout

    # Stop
    await service.stop(handle)
    record = await repo.find_by_name("integration-test")
    assert record.status == EnvironmentStatus.STOPPED

    # Destroy
    await service.destroy(handle)
    record = await repo.find_by_name("integration-test")
    assert record.status == EnvironmentStatus.DESTROYED
```

### CI Considerations

CI environments (GitHub Actions, GitLab CI) typically have Docker available via Docker-in-Docker or a host-mounted socket. Integration tests for this module require Docker and are tagged with `@pytest.mark.integration`. They do not run in the default `pytest` invocation (per doc 11 — CI runs unit tests by default, integration tests on demand).

gVisor (`sandbox` mode) tests require a Linux CI runner with KVM support. These are tagged `@pytest.mark.sandbox` and run only in dedicated security-testing pipelines.

---

## Module Layout

```
modules/backend/
├── models/
│   └── execution_environment.py          # SQLAlchemy model
├── schemas/
│   └── execution_environment.py          # Pydantic schemas (Create, Response, Handle)
├── repositories/
│   └── execution_environment.py          # Data access layer
├── services/
│   ├── execution_environment.py          # Main service
│   ├── container_backend.py              # Abstract backend interface + dataclasses
│   ├── docker_backend.py                 # Docker implementation
│   └── network_policy.py                 # Egress allowlist enforcement
├── tasks/
│   └── environment_maintenance.py        # Scheduled lifecycle maintenance

config/
├── settings/
│   └── environments.yaml                 # Environment templates and configuration
└── environments/
    └── dockerfiles/                      # Dockerfiles for environment images
        ├── scraper-python.Dockerfile
        ├── code-runner.Dockerfile
        └── headless-browser.Dockerfile

tests/
├── unit/services/
│   └── test_execution_environment.py
└── integration/services/
    └── test_execution_environment_docker.py
```

---

## What NOT to Do

- **Do not give agents access to Docker.** Agents never call `docker-py`, never see the Docker socket, never know they run in containers. The `ExecutionEnvironmentService` is infrastructure. Agents call tools; tools produce results.
- **Do not mount the Docker socket into containers.** This grants root-equivalent access to the host. There is no legitimate use case for this in agent execution.
- **Do not use `--privileged` containers.** This disables all security features. Use specific `cap_add` entries for the minimum capabilities needed (e.g., `SYS_ADMIN` for Chromium only).
- **Do not use `--network=host`.** This bypasses all network isolation. Containers always use the dedicated agent bridge network.
- **Do not store secrets in container images.** Images are cached, shared, and potentially pushed to registries. Secrets are injected at runtime via environment variables.
- **Do not skip the backend abstraction.** All callers go through `ExecutionEnvironmentService`, never through `DockerBackend` directly. Changing the container runtime should require changing one class, not every caller.
- **Do not use `:latest` tags in production.** Pin images by digest (`image@sha256:...`). Tag mutation is a real supply chain attack vector.
- **Do not create a separate orchestration system.** This module manages container lifecycle. Task orchestration belongs in the coordinator (doc 40), Temporal (Plan 15), and Taskiq (doc 14). Do not build a parallel scheduler.
- **Do not assume Docker is always available.** The feature is behind a flag (`execution_environments.enabled`). When disabled, all tasks execute `local`. Code paths that touch `ExecutionEnvironmentService` must check the flag first.

---

## Implementation Phases

This module is implemented after Plan 16 (Playbooks & Missions) and can proceed independently of Plan 15 (Temporal), though Tier 4 integration requires both.

### Phase 1: Foundation

- [ ] Create `config/settings/environments.yaml` with feature flag and one template (`code-runner`)
- [ ] Add `ExecutionEnvironmentsSchema` to `config_schema.py`
- [ ] Create `ExecutionEnvironment` model, repository, schemas
- [ ] Create `ContainerBackend` abstract interface and `DockerBackend` implementation
- [ ] Create `ExecutionEnvironmentService` with `resolve_or_create`, `execute_in_environment`, `stop`, `destroy`
- [ ] Write unit tests with mocked backend
- [ ] Write integration test with real Docker
- [ ] Alembic migration for `execution_environments` table

### Phase 2: Coordinator Integration

- [ ] Update coordinator to check `_execution_environment` in task metadata
- [ ] Route `container` and `sandbox` tasks through `ExecutionEnvironmentService`
- [ ] Add `scraper-python` and `headless-browser` templates
- [ ] Create Dockerfiles for each template
- [ ] Build and test images on Apple Silicon and Linux

### Phase 3: Network and Security

- [ ] Implement `apply_egress_policy()` with iptables rules
- [ ] Implement metadata endpoint blocking
- [ ] Add `network_extend` support for playbook steps
- [ ] Add gVisor detection and `sandbox` mode support
- [ ] Security audit: verify non-root, dropped caps, no socket mount

### Phase 4: Lifecycle Management

- [ ] Implement `archive()` and `restore()` (container commit/restore from image)
- [ ] Implement `run_lifecycle_maintenance()` scheduled task
- [ ] Add auto-stop, auto-archive, auto-destroy policy enforcement
- [ ] Add health monitoring scheduled task
- [ ] Observability: structured logs and session events for all lifecycle transitions

### Phase 5: Temporal Integration (Requires Plan 15)

- [ ] Add `execute_task_in_environment` Temporal Activity
- [ ] Update `AgentPlanWorkflow` to route containerized tasks to the new Activity
- [ ] Test crash recovery: Temporal retries after container failure
- [ ] Test long-lived environments across multiple Temporal workflow executions

### Phase 6: Cloud Backend (Future)

- [ ] Implement `ECSBackend` for AWS Fargate deployment
- [ ] Map volumes to EFS, network policy to Security Groups
- [ ] Test identical playbooks running locally (Docker) and in cloud (ECS)
- [ ] Optionally implement `K8sBackend` for Kubernetes deployment

---

## Glossary

| Term | Definition |
|------|-----------|
| **Execution environment** | An isolated container managed by the platform for agent task execution. Has its own filesystem, process tree, network namespace, and resource limits. |
| **Environment template** | YAML configuration defining the container image, resource limits, volume mounts, network policy, and lifecycle settings for a class of environments. |
| **Container backend** | The abstraction layer over the container runtime (Docker, ECS, Kubernetes). Implementations are swappable without changing callers. |
| **Long-lived environment** | A container that persists across multiple task executions (e.g., daily scheduled runs). Retains installed packages, cached data, and working state between runs. |
| **Ephemeral environment** | A container created for a single task execution and destroyed afterward. |
| **gVisor (runsc)** | Google's user-space kernel that intercepts all container syscalls. Provides VM-level isolation at container density. Required for `sandbox` mode. |
| **Egress allowlist** | The list of domains/IPs a container is permitted to reach. Empty list = deny all outbound traffic (P8). |
| **Environment handle** | A lightweight object returned by `resolve_or_create()` that holds the database record and backend reference. Passed to all subsequent operations on that environment. |
| **Archive** | Committing a container's filesystem state to a Docker image snapshot, then removing the running container. Preserves state while freeing compute resources. |
