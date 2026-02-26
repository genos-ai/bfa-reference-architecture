## Coding Standards

When working with this codebase, follow these standards without exception:

- **Absolute imports only.** Always `from modules.backend.core.config import ...`. Never relative imports (`from .foo`).
- **Centralized logging only.** Always `from modules.backend.core.logging import get_logger`. Never `import logging` directly.
- **Timezone-naive UTC datetimes.** Use `from modules.backend.core.utils import utc_now`. Never `datetime.utcnow()` (deprecated) or `datetime.now()` (local time).
- **No hardcoded values.** All configuration from `config/settings/*.yaml`. All secrets from `config/.env`. No hardcoded fallbacks in code.
- **Files must not exceed 1000 lines.** Target 400-500 lines. Split into focused submodules if larger.
- **`__init__.py` files must be minimal.** Docstring and necessary exports only. No business logic.
- **Layered architecture is strict.** API → Service → Repository → Model. Never skip layers.
- **Tools are thin adapters.** Tool functions call service methods. No business logic in tools.
