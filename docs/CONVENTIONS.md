# Code Conventions

## Python 3.10+ Compatibility

- Every module uses `from __future__ import annotations` for forward compatibility
- `TYPE_CHECKING` guards on imports used only for type hints (avoids circular imports)

## Code Style

- **Line length**: 100 characters (enforced by Ruff)
- **Ruff rules**: E, F, W, I, N, UP, B, A, SIM
- **Type checking**: Strict mypy — no implicit `Any`, `warn_return_any = true`

## Async Patterns

- **UI event handlers**: Use `page.run_task(coro)` to dispatch async operations from sync handlers
- **pytest**: Uses `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed

## Testing

- Test fixtures in `tests/conftest.py` provide in-memory `SQLiteBackend` via `tmp_path`
- Run tests: `pytest`
- Run single test: `pytest tests/unit/test_session_service.py`
- Run by name: `pytest -k "test_name"`

## Import Conventions

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some_module import SomeType  # Only for type hints
```

## Naming Conventions

- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

## Error Handling

- Services raise exceptions; UI layer catches and displays user-friendly messages
- Database errors wrapped in service layer
- Use custom exception classes for domain-specific errors
