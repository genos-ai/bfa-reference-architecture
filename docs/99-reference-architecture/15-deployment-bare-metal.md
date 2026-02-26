# 15 - Deployment: Bare Metal

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic deployment standard

---

## Context

Not every project runs on a cloud platform. Teams with dedicated servers, regulatory constraints that prohibit public cloud, or cost-sensitive deployments need a deployment model that runs directly on the host operating system — without Docker, Kubernetes, or managed services.

This module defines that model using standard Linux infrastructure: systemd for process management, nginx for reverse proxy and TLS termination, and a symlink-based release strategy that enables instant rollback. The key insight is that the deployment model should not constrain the scaling path — the same application code runs on a single server with everything co-located, then scales to separate database servers, multiple application servers behind a load balancer, and eventually managed services if the scale justifies the cost.

The application code is identical regardless of whether it deploys to bare metal or Azure (22). This document covers only the infrastructure: server setup, service configuration, release management, backup procedures, and monitoring integration. It implements the security standards (17) at the infrastructure level and integrates with background tasks (19) for worker and scheduler service definitions.

---

## Deployment Philosophy

### No Containers

Applications run directly on the host operating system. No Docker, no Kubernetes.

Rationale:
- Simpler debugging and troubleshooting
- Direct access to system resources
- No container orchestration complexity
- Lower overhead for small deployments

### Process Management: systemd

All services managed by systemd:
- Automatic restart on failure
- Log management via journald
- Service dependencies
- Resource limits

### Scaling Path

MVP to Production without re-architecture:
1. Single server with all components
2. Separate database to dedicated server
3. Add application servers behind load balancer
4. Add Redis cluster if needed
5. Managed services when scale justifies cost

---

## Server Setup

### Operating System

Standard: Ubuntu LTS (22.04 or latest LTS)

Rationale:
- Widely used, well documented
- Long-term support
- Good Python ecosystem support

### System Requirements

Minimum for MVP:
- CPU: 4 cores
- RAM: 8 GB
- Storage: 100 GB SSD

Recommended for production:
- CPU: 8+ cores
- RAM: 32+ GB
- Storage: 500+ GB SSD

### Initial Configuration

1. Update system packages
2. Configure firewall (ufw)
3. Setup SSH key authentication, disable password auth
4. Create application user (non-root)
5. Configure automatic security updates
6. Setup log rotation

---

## Python Environment

### Python Installation

Use pyenv for Python version management:
- Install pyenv
- Install required Python version
- Create project-specific virtual environment

### Virtual Environment

Each application has its own virtual environment:
- Location: `/opt/{app-name}/venv/`
- Owned by application user
- Activated by systemd service

### Dependency Installation

```bash
cd /opt/{app-name}
source venv/bin/activate
pip install -r requirements.txt
```

Pin pip and setuptools versions for reproducibility.

---

## Application Deployment

### Directory Structure

```
/opt/{app-name}/
├── current/              # Symlink to active release
├── releases/             # Release directories
│   ├── 20250127_120000/
│   └── 20250127_150000/
├── shared/               # Persistent files
│   ├── logs/
│   └── uploads/
├── venv/                 # Virtual environment
└── .env                  # Environment variables
```

### Deployment Process

1. Create new release directory with timestamp
2. Clone/copy application code to release directory
3. Install dependencies in virtual environment
4. Run database migrations
5. Update `current` symlink to new release
6. Restart application service
7. Verify health checks
8. Clean up old releases (keep last 5)

### Rollback

Rollback is symlink change:
1. Update `current` symlink to previous release
2. Restart application service
3. Verify health checks

Database rollback if needed (separate process with migration downgrade).

---

## Service Configuration

### systemd Service Unit

Location: `/etc/systemd/system/{app-name}.service`

Example configuration:

```ini
[Unit]
Description=Application API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User={app-user}
Group={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
TimeoutStopSec=35
KillMode=mixed
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
```

### Service Commands

```bash
sudo systemctl start {app-name}
sudo systemctl stop {app-name}
sudo systemctl restart {app-name}
sudo systemctl status {app-name}
sudo systemctl enable {app-name}  # Start on boot
```

### Multiple Services

For applications with multiple components:
- `{app-name}-api.service` - FastAPI application
- `{app-name}-worker.service` - Taskiq worker (background tasks)
- `{app-name}-scheduler.service` - Taskiq scheduler (cron jobs)

Use `PartOf=` and `Requires=` for dependencies.

### Graceful Shutdown

All services handle shutdown signals gracefully:

**Shutdown sequence:**

| Step | Timeout | Action |
|------|---------|--------|
| 1 | 0s | Receive SIGTERM, stop accepting new requests |
| 2 | 0-30s | Complete in-flight requests |
| 3 | 30s | Force-close remaining connections |
| 4 | 30-35s | Close database connections, flush logs |
| 5 | 35s | Process exits |

**Health check during shutdown:**

Return 503 once shutdown begins so load balancer stops routing:
```python
@app.get("/health/ready")
async def readiness():
    if app.state.shutting_down:
        raise HTTPException(503, "Shutting down")
    return {"status": "healthy"}
```

---

## Reverse Proxy

### Standard: nginx

nginx serves as reverse proxy and static file server.

Configuration location: `/etc/nginx/sites-available/{app-name}`

### Configuration Elements

- Listen on 80 (redirect to 443)
- Listen on 443 with SSL
- Proxy pass to application (localhost:8000)
- WebSocket upgrade handling
- Static file serving if applicable
- Security headers

### SSL Certificates

Use Let's Encrypt with certbot:
- Automatic renewal via systemd timer
- Certificate in `/etc/letsencrypt/live/{domain}/`

---

## Database Deployment

### PostgreSQL Setup

1. Install PostgreSQL from official repository
2. Create database and user
3. Configure `pg_hba.conf` for application access
4. Configure backups

### Connection Security

- Application connects via localhost or private network
- SSL for remote connections
- Strong passwords, stored in environment variables

### Backup Configuration

Daily backups via pg_dump:
- Full database dump
- Compress with gzip
- Copy to backup location (separate disk or remote)
- Retention: 30 days

---

## Redis Deployment

### Installation

Install from official repository for latest stable version.

### Configuration

Key settings:
- maxmemory: Set based on available RAM
- maxmemory-policy: allkeys-lru
- appendonly: yes (if persistence needed)

### Security

- Bind to localhost only
- Require password (stored in environment)
- Disable dangerous commands

---

## Background Tasks

### Worker Service

Systemd service for Taskiq worker:

```ini
[Unit]
Description=Taskiq Worker
After=network.target redis.service

[Service]
Type=simple
User={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/taskiq worker tasks.broker:broker
Restart=always
RestartSec=5
TimeoutStopSec=35

[Install]
WantedBy=multi-user.target
```

### Scheduler Service

Only one scheduler instance should run:

```ini
[Unit]
Description=Taskiq Scheduler
After=network.target redis.service

[Service]
Type=simple
User={app-user}
WorkingDirectory=/opt/{app-name}/current
EnvironmentFile=/opt/{app-name}/.env
ExecStart=/opt/{app-name}/venv/bin/taskiq scheduler tasks.scheduler:scheduler
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Environment Management

### Environment Variables

Stored in `/opt/{app-name}/.env`:
- Not in version control
- Owned by application user, mode 600
- Loaded by systemd service

### Configuration Updates

1. Update .env file
2. Restart affected services
3. Verify health checks

### Secret Rotation

Process for rotating secrets:
1. Generate new secret
2. Update .env file
3. Restart services
4. Verify operation
5. Revoke old secret (if external)

---

## Monitoring Setup

### Log Collection

Logs written to `/opt/{app-name}/shared/logs/`:
- Application logs (JSON format)
- Access logs
- Error logs

Log rotation via logrotate:
- Daily rotation
- Compress after 1 day
- Keep 30 days

### Health Check Monitoring

External monitoring service (UptimeRobot, Healthchecks.io, or similar):
- Check /health endpoint every minute
- Alert on failure

### Resource Monitoring

Options for resource monitoring:
- Netdata (lightweight, self-hosted)
- Prometheus + node_exporter
- Simple scripts with alerts

---

## Scaling Considerations

### Vertical Scaling

First scaling step: Larger server
- More CPU for concurrent requests
- More RAM for database caching
- Faster storage for database

### Horizontal Scaling

When single server insufficient:

**Database:**
- Move to dedicated server
- Consider managed PostgreSQL
- Read replicas if read-heavy

**Application:**
- Multiple application servers
- Load balancer (nginx or cloud LB)
- Sticky sessions if needed

**Redis:**
- Move to dedicated server
- Redis Sentinel for HA
- Redis Cluster for scaling

**Workers:**
- Multiple workers across servers
- Same queue, competing consumers
- Scheduler runs on single instance only

---

## Disaster Recovery

### Backup Verification

Monthly:
- Restore backup to test environment
- Verify data integrity
- Test application against restored data

### Recovery Procedures

Documented procedures for:
- Full server failure
- Database corruption
- Accidental data deletion
- Security breach

### Recovery Time Objectives

Define and test:
- RPO (Recovery Point Objective): Maximum data loss acceptable
- RTO (Recovery Time Objective): Maximum downtime acceptable

Typical targets:
- RPO: 1 hour (continuous WAL archiving)
- RTO: 4 hours (restore from backup)

---

## Deployment Checklist

### Pre-Deployment

- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Database migrations tested
- [ ] Environment variables prepared
- [ ] Rollback plan documented

### Deployment

- [ ] Notify team of deployment
- [ ] Deploy to staging, verify
- [ ] Deploy to production
- [ ] Verify health checks
- [ ] Smoke test critical paths

### Post-Deployment

- [ ] Monitor error rates
- [ ] Monitor performance metrics
- [ ] Confirm no regressions
- [ ] Update deployment log
- [ ] Clean up old releases
