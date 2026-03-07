# Windows No-Console Subprocess Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent packaged Windows GUI builds of Misaka from flashing a `cmd` console window when Claude conversations start, while keeping all subprocess-based tool checks and npm operations running silently in the background.

**Architecture:** Move Windows subprocess behavior behind a single platform utility that provides hidden-window launch kwargs and wrapper-command normalization for `.cmd`/`.bat` executables. Split Claude CLI discovery into a general "find any working Claude command" path and an SDK-safe "prefer direct executable, avoid wrapper scripts" path so `ClaudeSDKClient` does not receive `claude.cmd` as its `cli_path` in packaged GUI builds.

**Tech Stack:** Python 3.10+, asyncio subprocess APIs, subprocess, PyInstaller, pytest

---

### Task 1: Add failing tests for Windows hidden subprocess helpers

**Files:**
- Modify: `tests/unit/test_env_check_service.py:278-330`
- Modify: `tests/unit/test_update_check_service.py:152-245`
- Create/Modify: `tests/unit/test_platform.py`
- Modify: `misaka/utils/platform.py:21-160`

**Step 1: Write the failing test**

```python
from misaka.utils.platform import build_background_subprocess_kwargs, wrap_windows_script_command


def test_wrap_windows_script_command_wraps_cmd_file() -> None:
    command = wrap_windows_script_command("C:/Users/test/AppData/Roaming/npm/claude.cmd", ["--version"])
    assert command == ["cmd.exe", "/d", "/s", "/c", '""C:/Users/test/AppData/Roaming/npm/claude.cmd" --version"']


def test_build_background_subprocess_kwargs_returns_windows_startupinfo() -> None:
    kwargs = build_background_subprocess_kwargs()
    assert kwargs["creationflags"] != 0
    assert kwargs["startupinfo"] is not None
```

Also update existing service tests so they stop expecting `cmd` / `/c` as the first two arguments and instead assert they call the shared wrapper helper behavior.

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py tests/unit/test_platform.py -k "windows or subprocess or wrapper" -v`
Expected: FAIL because the platform helper functions and updated call expectations do not exist yet.

**Step 3: Write minimal implementation**

```python
def build_background_subprocess_kwargs() -> dict[str, object]:
    if not IS_WINDOWS:
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def wrap_windows_script_command(binary_path: str, args: list[str]) -> list[str]:
    if IS_WINDOWS and binary_path.lower().endswith((".cmd", ".bat")):
        cmdline = subprocess.list2cmdline([binary_path, *args])
        return ["cmd.exe", "/d", "/s", "/c", f'"{cmdline}"']
    return [binary_path, *args]
```

Then make `subprocess_creation_flags()` reuse the new helper rather than being the only Windows suppression hook.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py tests/unit/test_platform.py -k "windows or subprocess or wrapper" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py tests/unit/test_platform.py misaka/utils/platform.py
git commit -m "fix: centralize hidden Windows subprocess launch behavior"
```

### Task 2: Add failing tests for SDK-safe Claude CLI resolution

**Files:**
- Modify: `tests/unit/test_claude_sdk_integration.py:406-444`
- Create/Modify: `tests/unit/test_platform.py`
- Modify: `misaka/utils/platform.py:66-156`
- Modify: `misaka/services/chat/claude_service.py:167-173`

**Step 1: Write the failing test**

```python
def test_find_claude_sdk_binary_prefers_exe_over_cmd() -> None:
    with patch("misaka.utils.platform.IS_WINDOWS", True), \
         patch("misaka.utils.platform._get_claude_candidate_paths", return_value=[
             "C:/npm/claude.cmd",
             "C:/npm/claude.exe",
         ]), \
         patch("misaka.utils.platform._validate_claude_binary", return_value=True):
        assert find_claude_sdk_binary() == "C:/npm/claude.exe"


def test_build_options_uses_sdk_safe_claude_binary(claude_service, mock_sdk) -> None:
    mock_sdk.ClaudeAgentOptions = MagicMock(return_value=MagicMock())
    with patch("misaka.services.chat.claude_service.find_claude_sdk_binary", return_value="C:/npm/claude.exe"):
        options = claude_service._build_options()
        assert options.cli_path == "C:/npm/claude.exe"
```

Add a companion test asserting the fallback still returns `.cmd` only when no direct executable exists.

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_claude_sdk_integration.py tests/unit/test_platform.py -k "sdk_binary or cli_path or claude" -v`
Expected: FAIL because `find_claude_sdk_binary()` does not exist and `ClaudeService` still imports `find_claude_binary()`.

**Step 3: Write minimal implementation**

```python
def find_claude_sdk_binary() -> str | None:
    if not IS_WINDOWS:
        return find_claude_binary()

    direct_candidates = [p for p in _get_claude_candidate_paths() if Path(p).suffix.lower() in {".exe", ""}]
    wrapper_candidates = [p for p in _get_claude_candidate_paths() if Path(p).suffix.lower() in {".cmd", ".bat"}]

    for path in [*direct_candidates, *wrapper_candidates]:
        if _validate_claude_binary(path):
            return path

    found = shutil.which("claude", path=get_expanded_path())
    if found and _validate_claude_binary(found):
        return found
    return None
```

Then change `misaka/services/chat/claude_service.py` to import and use `find_claude_sdk_binary()` when setting `options.cli_path`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_claude_sdk_integration.py tests/unit/test_platform.py -k "sdk_binary or cli_path or claude" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_claude_sdk_integration.py tests/unit/test_platform.py misaka/utils/platform.py misaka/services/chat/claude_service.py
git commit -m "fix: avoid wrapper-based Claude CLI launch in Windows GUI builds"
```

### Task 3: Refactor Windows tool-version and npm invocations to use shared background helpers

**Files:**
- Modify: `misaka/services/skills/env_check_service.py:335-373`
- Modify: `misaka/services/file/update_check_service.py:97-160`
- Modify: `misaka/services/file/update_check_service.py:231-268`
- Modify: `misaka/utils/platform.py:200-260`
- Modify: `tests/unit/test_env_check_service.py:278-330`
- Modify: `tests/unit/test_update_check_service.py:152-245`

**Step 1: Write the failing test**

```python
async def test_get_version_windows_cmd_wrapper_uses_shared_wrapper(service) -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"v18.0.0\n", b"")
    mock_proc.returncode = 0

    with patch("misaka.services.skills.env_check_service.wrap_windows_script_command", return_value=["cmd.exe", "/d"]), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await service._get_version("C:/npm/node.cmd", "--version")
        mock_exec.assert_called_once()
        assert mock_exec.call_args[0][:2] == ("cmd.exe", "/d")
```

And similarly for `perform_update()` / `_fetch_version_via_npm_cli()` asserting they delegate command construction to the shared platform helper and still pass hidden-window kwargs.

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py -k "wrapper or npm or version" -v`
Expected: FAIL because the services still build wrapper commands inline.

**Step 3: Write minimal implementation**

```python
from misaka.utils.platform import (
    build_background_subprocess_kwargs,
    wrap_windows_script_command,
)

cmd = wrap_windows_script_command(binary_path, [version_flag])
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    **build_background_subprocess_kwargs(),
)
```

Apply the same pattern for npm update and npm version lookup so all Windows subprocess callers use one implementation path.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py -k "wrapper or npm or version" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add misaka/services/skills/env_check_service.py misaka/services/file/update_check_service.py misaka/utils/platform.py tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py
git commit -m "refactor: route Windows background subprocesses through shared helpers"
```

### Task 4: Add focused regression verification for packaged-GUI subprocess behavior

**Files:**
- Test: `tests/unit/test_platform.py`
- Test: `tests/unit/test_claude_sdk_integration.py`
- Test: `tests/unit/test_env_check_service.py`
- Test: `tests/unit/test_update_check_service.py`

**Step 1: Run focused unit tests**

Run: `pytest tests/unit/test_platform.py tests/unit/test_claude_sdk_integration.py tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py -v`
Expected: PASS

**Step 2: Run the broader related suite**

Run: `pytest tests/unit/test_claude_service.py tests/unit/test_claude_sdk_integration.py tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py tests/unit/test_mcp_service.py -v`
Expected: PASS

**Step 3: Manual verification checklist**

- Build the Windows package with `pyinstaller misaka.spec`.
- Launch the packaged `Misaka.exe` by double-clicking it from Explorer.
- Start a new chat and send a message that causes Claude CLI startup.
- Confirm no `cmd`/console window flashes during the first response.
- Open the app’s update check path and dependency check path.
- Confirm update check, version detection, and tool checks still work with no visible terminal window.
- If you have a machine where only `claude.cmd` exists, confirm the app still detects Claude correctly and either uses a non-wrapper SDK path or degrades without flashing a console.

**Step 4: Commit**

```bash
git add tests/unit/test_platform.py tests/unit/test_claude_sdk_integration.py tests/unit/test_env_check_service.py tests/unit/test_update_check_service.py misaka/utils/platform.py misaka/services/chat/claude_service.py misaka/services/skills/env_check_service.py misaka/services/file/update_check_service.py
git commit -m "fix: keep Windows subprocesses hidden in packaged builds"
```
