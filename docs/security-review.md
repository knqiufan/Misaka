# Misaka Security Review

**Date**: 2026-02-23
**Reviewer**: QA Engineer (automated review)
**Scope**: All source code in `misaka/`

---

## 1. Path Traversal Protection

### `misaka/utils/path_safety.py`

**Status: PASS (with bug fix applied)**

- `is_path_safe()` resolves both paths via `Path.resolve()` before comparison, eliminating `..` and symlink-based traversals.
- `is_root_path()` **had a bug**: it compared a `Path` object to a `str` (`resolved == resolved.anchor`), which always returned False on Windows. **Fixed** by using `resolved == resolved.parent` -- a root path is one whose parent is itself.
- `sanitize_filename()` uses a strict allowlist of safe characters (alphanumeric, `.`, `-`, `_`), replacing everything else with `_`.

### `misaka/services/file_service.py`

**Status: PASS**

- `scan_directory()` rejects filesystem roots via `is_root_path()`.
- `read_file_preview()` validates file paths against an optional `base_dir` using `is_path_safe()`.
- Directory scanning skips hidden files (except `.env*`) and ignores common directories (`node_modules`, `.git`, `__pycache__`, etc.).
- `PermissionError` during directory iteration is caught and returns empty results (no information leak).

**Recommendation**: Consider adding a maximum file size check in `read_file_preview()` before reading (there is `MAX_PREVIEW_SIZE` defined in `file_utils.py` but it is not enforced in the preview reader).

---

## 2. API Key Storage

### `misaka/db/sqlite_backend.py`

**Status: ACCEPTABLE (with caveats)**

- API keys are stored in the `api_providers` table as plaintext in the `api_key` column.
- The database file is stored in `~/.misaka/misaka.db` with standard filesystem permissions.
- SQLite WAL mode is used, which creates `-wal` and `-shm` companion files that may contain key material.

**Positive findings**:
- No API keys are logged by the service layer. `ProviderService` and `ClaudeService` only log provider IDs and names, never keys.
- No API keys are hardcoded anywhere in the codebase.
- The `_sanitize_env()` function in `claude_service.py` filters out non-string values and control characters, but does not log the sanitized values.

**Recommendations**:
- Consider encrypting the `api_key` column at rest (e.g., using `cryptography.fernet` with a key derived from a machine-specific secret).
- Ensure the database file has restrictive permissions (0600) on Unix systems.
- Add a `__repr__` override to `ApiProvider` that redacts the `api_key` field to prevent accidental logging.

---

## 3. Input Validation

### User Input

**Status: PASS**

- Session titles, model names, and system prompts are stored as-is but always passed through parameterized SQL queries (no SQL injection risk).
- The SQLite backend uses `?` parameter placeholders exclusively -- no string formatting in SQL queries.
- Settings are stored as key-value pairs with proper `INSERT ... ON CONFLICT ... UPDATE` syntax.
- The `role` column has a CHECK constraint: `CHECK(role IN ('user', 'assistant'))`.
- The `status` column on tasks has a CHECK constraint: `CHECK(status IN ('pending', 'in_progress', 'completed', 'failed'))`.

### File Paths

- File paths provided by users (for file preview) are validated against `base_dir` when provided.
- Working directories for sessions are stored as-is but are only used as parameters to the Claude SDK's `cwd` option.

**No validation gaps found.**

---

## 4. Command Injection Protection

### `misaka/services/mcp_service.py`

**Status: PASS**

- `MCPServerProcess.start()` uses `asyncio.create_subprocess_exec()` which does NOT use shell=True. Commands and arguments are passed as separate elements, preventing shell injection.
- Environment variables for MCP servers are merged from config files, not from user input.
- On Windows, `stop()` uses `taskkill /T /F /PID` with `DEVNULL` for stdout/stderr, preventing output injection.

### `misaka/utils/platform.py`

**Status: PASS (with note)**

- `_validate_claude_binary()` calls `subprocess.run([path, "--version"])` where `path` comes from a controlled search of known directories.
- On Windows, `shell=True` is used ONLY when the path ends with `.cmd` or `.bat` (line 110). This is a necessary Windows workaround for `.cmd` wrappers but limits the attack surface since the path is validated via `os.path.isfile()` first.
- `find_git_bash()` only searches hardcoded paths and `shutil.which("git")` -- no user-controllable input.

### `misaka/services/claude_service.py`

**Status: PASS**

- `_sanitize_env()` and `_sanitize_env_value()` strip null bytes and control characters from environment variables before passing to subprocess.
- The `_resolve_script_from_cmd()` function reads `.cmd` files and extracts `.js` paths via regex. The result is validated with `os.path.isfile()` before use.
- Environment variables from `ApiProvider.extra_env` are parsed from JSON and only string values are accepted.

---

## 5. Permission System

### `misaka/services/permission_service.py`

**Status: PASS**

- Permission requests use unique IDs generated from `time.time()` + `os.urandom(3)`.
- Pending permissions have a 5-minute timeout (`TIMEOUT_SECONDS = 300`), after which they are automatically denied.
- `_cleanup_expired()` is called on every `register()` and `has_pending()` call to prevent memory leaks.
- Double-resolve is handled: `resolve()` pops the entry atomically, so a second call returns False.
- The `can_use_tool` callback in `ClaudeService` properly awaits the user's decision via an asyncio.Future.

### Permission Mode

- The `dangerously_skip_permissions` setting bypasses the permission dialog entirely. This is a user-opted-in behavior (must be explicitly enabled in settings).
- The setting name contains "dangerously" as a clear warning.

**Recommendation**: Log when bypass mode is activated (already done implicitly via the SDK option).

---

## 6. Markdown / XSS Safety

### Flet Markdown Rendering

**Status: PASS (inherently safe)**

- Flet's `ft.Markdown` widget renders Markdown to native UI controls, NOT to a web browser DOM. There is no HTML rendering context, so traditional XSS attacks (script injection via `<script>`, `onerror`, etc.) are not applicable.
- The Flet framework does not support arbitrary HTML execution within Markdown widgets.
- Code blocks are rendered via `ft.Markdown` with syntax highlighting, not via `eval()` or `exec()`.

**No XSS risk identified in the Flet rendering pipeline.**

---

## 7. Database Security

### SQL Injection

**Status: PASS**

- All SQL queries use parameterized statements (`?` placeholders).
- No string formatting or f-strings are used in SQL construction.
- The only dynamic table name usage is in `migrations.py:_get_column_names()` with `f"PRAGMA table_info({table})"`, but `table` is always a hardcoded constant string, never user input.

### Foreign Key Cascading

- `PRAGMA foreign_keys = ON` is set on connection initialization.
- Messages and tasks have `ON DELETE CASCADE` foreign keys to `chat_sessions`, ensuring no orphaned records.

---

## 8. SeekDB Backend

### `misaka/db/seekdb_backend.py`

**Status: ACCEPTABLE**

- The SeekDB backend is only loaded on non-Windows platforms and only when `pyseekdb` is installed.
- All operations catch exceptions and log errors without crashing.
- Document data is JSON-serialized before storage, preventing type confusion.
- The `_delete_by_field()` helper iterates all documents to find matches -- this could be slow with large collections but is not a security issue.

---

## 9. Additional Findings

### Logging

- Logging is configured to both stderr and a file (`~/.misaka/misaka.log`).
- No API keys or sensitive data are logged at any log level.
- Exception stack traces are logged at ERROR level but do not contain key material.

### Dependencies

- `flet>=0.27.0` -- GUI framework (trusted, maintained by Google)
- `claude-agent-sdk>=0.1.5` -- Anthropic SDK (first-party)
- `watchdog>=4.0.0` -- File system monitoring (well-known library)
- `aiofiles>=24.0.0` -- Async file I/O (no known vulnerabilities)
- `Pygments>=2.18.0` -- Syntax highlighting (well-known library)
- `anyio>=4.0.0` -- Async I/O abstraction (no known vulnerabilities)

**No known CVEs affecting these versions at time of review.**

### Error Handling

- `ClaudeService.send_message()` catches all exception types and routes them to `on_error` callbacks. It never crashes the application on SDK errors.
- `ServiceContainer.close()` catches all exceptions during cleanup to ensure graceful shutdown.

---

## Summary

| Category | Status | Severity |
|----------|--------|----------|
| Path Traversal | FIXED (is_root_path bug) | Medium |
| API Key Storage | ACCEPTABLE | Low |
| Input Validation | PASS | - |
| Command Injection | PASS | - |
| Permission System | PASS | - |
| Markdown XSS | PASS (N/A for Flet) | - |
| SQL Injection | PASS | - |
| Logging (key leak) | PASS | - |

**Bug fixed during review**: `is_root_path()` in `misaka/utils/path_safety.py` compared a `Path` object to a string, always returning False. This meant `scan_directory("/")` or `scan_directory("C:\\")` would NOT be rejected. Fixed by using `resolved == resolved.parent`.

**Total issues found**: 1 bug (fixed), 2 minor recommendations (API key encryption, MAX_PREVIEW_SIZE enforcement).
