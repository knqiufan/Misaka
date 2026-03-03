# Misaka 软件在线更新检查与自动安装 — 解决方案说明书

## 1. 概述

### 1.1 文档目的

本文档描述 Misaka 桌面应用在设置模块中实现**在线更新检查**与**自动安装**功能的完整技术方案，供开发团队参考与实施。

### 1.2 当前状态

| 模块 | 状态 | 说明 |
|------|------|------|
| Claude Code CLI 更新 | ✅ 已实现 | `UpdateCheckService` 检查 npm 版本并执行 `npm install -g` |
| Misaka 应用更新 | ❌ 未实现 | 设置页有 UI 占位，点击显示「更新服务器尚未配置」 |
| 版本来源 | `misaka.__version__` | 与 `pyproject.toml` 同步 |

### 1.3 目标范围

- **更新检查**：检测是否有新版本可用
- **手动检查**：用户在设置中点击「检查更新」
- **启动时检查**（可选）：应用启动时静默检查
- **自动安装**：根据分发方式执行相应安装流程

---

## 2. 分发模式与更新策略

Misaka 存在两种主要分发方式，更新逻辑需分别处理：

### 2.1 分发模式

| 模式 | 识别方式 | 更新方式 |
|------|----------|----------|
| **A. PyInstaller 独立可执行文件** | `sys.frozen == True` 或 `getattr(sys, 'frozen', False)` | 下载新安装包，引导用户安装 |
| **B. pip 安装** | 非 frozen，可检测 `pip show misaka` | `pip install -U misaka` |

### 2.2 推荐策略

- **模式 A**：以 **GitHub Releases** 为版本与下载源，不执行自动覆盖（安全与权限考虑），而是：
  - 下载安装包到临时目录
  - 打开下载目录或直接打开安装包
  - 提示用户手动完成安装
- **模式 B**：执行 `pip install -U misaka`，可真正实现「自动安装」

---

## 3. 版本信息源设计

### 3.1 方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **GitHub Releases API** | 无需自建服务，与发布流程天然集成 | 需配置 repo，有 API 限流 |
| **自建 JSON 接口** | 可控、可扩展 | 需维护服务器 |
| **PyPI API** | 与 pip 模式一致 | 仅适用于 pip 安装，不包含 exe 下载链接 |

### 3.2 推荐：GitHub Releases API

适用于 PyInstaller 与 pip 两种模式：

- **版本号**：`/repos/{owner}/{repo}/releases/latest` 的 `tag_name`（如 `v0.1.1`）
- **下载链接**：`assets` 中按平台筛选的 `browser_download_url`
- **发布说明**：`body` 字段，用于更新弹窗展示

**API 示例：**

```
GET https://api.github.com/repos/{owner}/{repo}/releases/latest
```

**响应示例（简化）：**

```json
{
  "tag_name": "v0.1.1",
  "name": "Misaka 0.1.1",
  "body": "## 更新内容\n- 修复 xxx\n- 新增 yyy",
  "assets": [
    {
      "name": "Misaka-0.1.1-win64.zip",
      "browser_download_url": "https://github.com/.../Misaka-0.1.1-win64.zip",
      "content_type": "application/zip"
    }
  ]
}
```

### 3.3 备选：自建 JSON 清单

若希望完全自控，可维护一个 manifest 文件：

```json
{
  "version": "0.1.1",
  "release_date": "2025-03-03",
  "downloads": {
    "windows": "https://.../Misaka-0.1.1-win64.zip",
    "darwin": "https://.../Misaka-0.1.1-macos.dmg",
    "linux": "https://.../Misaka-0.1.1-linux.tar.gz"
  },
  "changelog": "## 更新内容\n..."
}
```

---

## 4. 架构设计

### 4.1 服务拆分建议

为避免与现有 Claude Code 更新逻辑混淆，建议新增 **Misaka 专用** 更新服务：

```
misaka/services/file/
├── update_check_service.py      # 现有：Claude Code CLI 更新
└── misaka_update_service.py    # 新增：Misaka 应用更新
```

### 4.2 数据模型

```python
# misaka/services/file/misaka_update_service.py

@dataclass
class MisakaUpdateResult:
    """Misaka 应用更新检查结果。"""

    current_version: str          # 当前版本，如 "0.1.0"
    latest_version: str | None    # 最新版本，如 "0.1.1"
    update_available: bool        # 是否有更新
    checked_at: str               # ISO 时间戳
    download_url: str | None      # 安装包下载链接（frozen 模式）
    release_notes: str | None     # 发布说明
    error: str | None             # 检查失败时的错误信息
```

### 4.3 状态扩展

在 `AppState` 中增加 Misaka 更新相关状态：

```python
# misaka/state.py

# --- Misaka update state ---
self.misaka_update_result: MisakaUpdateResult | None = None
self.misaka_update_dismissed: bool = False
self.misaka_update_in_progress: bool = False
```

**说明**：与 `update_check_result`（Claude Code）分离，避免混淆。

### 4.4 配置项

```python
# misaka/config.py 或 SettingKeys

# 更新检查 URL（可配置，便于自建）
MISAKA_UPDATE_CHECK_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"

# 或从环境变量读取
MISAKA_UPDATE_REPO = os.environ.get("MISAKA_UPDATE_REPO", "owner/repo")
```

---

## 5. 核心流程设计

### 5.1 更新检查流程

```
用户点击「检查更新」或启动时静默检查
    |
    v
MisakaUpdateService.check_for_update()
    |
    +-- 1. 获取当前版本：misaka.__version__
    |
    +-- 2. 获取最新版本：
    |       - HTTP GET GitHub API /releases/latest
    |       - 解析 tag_name（去除 "v" 前缀）
    |
    +-- 3. 版本比较：_compare_versions(current, latest)
    |
    +-- 4. 若为 frozen 模式，从 assets 中按平台筛选下载 URL
    |
    v
返回 MisakaUpdateResult
```

### 5.2 版本比较逻辑

复用现有 `UpdateCheckService._compare_versions` 的语义，或提取为公共工具：

```python
# 版本格式：x.y.z
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

def _compare_versions(current: str, latest: str) -> bool:
    """返回 True 表示 latest > current。"""
    # 解析、比较 (major, minor, patch)
```

### 5.3 安装流程（按模式）

**模式 A：PyInstaller 独立可执行文件**

```
用户点击「立即更新」
    |
    v
MisakaUpdateService.perform_update()
    |
    +-- 1. 下载安装包到临时目录（如 %TEMP%/Misaka/updates/）
    |
    +-- 2. 可选：校验文件（如 SHA256）
    |
    +-- 3. 打开下载目录或直接打开安装包
    |       - Windows: os.startfile(path) 或 subprocess.run(["explorer", "/select", path])
    |       - macOS: subprocess.run(["open", "-R", path])
    |       - Linux: 使用 xdg-open 或等效
    |
    +-- 4. 提示用户完成安装并重启应用
    |
    v
返回 True（下载成功）
```

**模式 B：pip 安装**

```
用户点击「立即更新」
    |
    v
MisakaUpdateService.perform_update()
    |
    +-- 1. 执行 subprocess: pip install -U misaka
    |
    +-- 2. 解析 stdout/stderr，通过 on_progress 回调反馈进度
    |
    +-- 3. 若成功，提示用户重启应用
    |
    v
返回 True/False
```

---

## 6. 设置模块 UI 设计

### 6.1 现有结构

`_build_misaka_update_section()` 已存在，包含：

- 标题：「Misaka 更新」
- 描述：「检查 Misaka 应用更新」
- 当前版本显示
- 「检查更新」按钮（目前仅显示 SnackBar）

### 6.2 扩展后 UI 状态

| 状态 | 显示内容 |
|------|----------|
| 未检查 | 当前版本 + 「检查更新」按钮 |
| 检查中 | 当前版本 + 加载动画 + 「检查中」 |
| 已是最新 | 当前版本 + 最新版本 + 「已是最新」徽章 |
| 有更新 | 当前版本 + 最新版本 + 「有更新」徽章 + 「立即更新」按钮 |
| 更新中 | 进度文案 + 加载动画 |
| 检查失败 | 错误信息 + 「重试」按钮 |

### 6.3 可选：设置项

- **启动时检查更新**：布尔开关，默认开启
- **检查频率**：如「每次启动」「每日」「每周」（可选，实现复杂度较高）

---

## 7. 实现细节

### 7.1 平台与资产匹配

GitHub Releases 的 `assets` 需按平台筛选：

```python
def _get_asset_for_platform(assets: list[dict], platform: str) -> dict | None:
    """根据平台选择安装包。"""
    # platform: "win32", "darwin", "linux"
    patterns = {
        "win32": ["win", "windows", ".exe", ".zip"],
        "darwin": ["mac", "darwin", "osx", ".dmg", ".app"],
        "linux": ["linux", ".tar"],
    }
    for a in assets:
        name = a.get("name", "").lower()
        if any(p in name for p in patterns.get(platform, [])):
            return a
    return None
```

### 7.2 下载实现

- 使用 `urllib.request` 或 `aiohttp` 进行下载
- 支持 `on_progress` 回调（已下载字节数 / 总字节数）
- 大文件建议使用分块下载，避免内存占用过大

### 7.3 错误处理

| 场景 | 处理方式 |
|------|----------|
| 网络超时 | 返回 `MisakaUpdateResult.error = "网络超时"` |
| 非 200 响应 | 记录错误，返回 `error` 字段 |
| API 限流 | 重试或提示稍后再试 |
| 无匹配资产 | 提示「当前平台暂无可用安装包」 |
| 版本解析失败 | 保守处理，视为无更新 |

### 7.4 安全考虑

- 使用 HTTPS
- 下载后可选校验 SHA256（若 manifest 提供）
- 不自动执行任意二进制，仅引导用户安装

---

## 8. 文件结构变更清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新增 | `misaka/services/file/misaka_update_service.py` | Misaka 更新服务 |
| 修改 | `misaka/services/__init__.py` | 导出 `MisakaUpdateService` |
| 修改 | `misaka/main.py` | 注册 `misaka_update_service`，可选启动时检查 |
| 修改 | `misaka/state.py` | 添加 `misaka_update_result` 等状态 |
| 修改 | `misaka/ui/settings/pages/settings_page.py` | 实现 `_build_misaka_update_section` 完整逻辑 |
| 可选 | `misaka/ui/status/misaka_update_banner.py` | 有更新时在聊天页顶部显示横幅 |
| 可选 | `misaka/db/models.py` | 若需持久化「启动时检查」等设置 |
| 新增 | `tests/unit/test_misaka_update_service.py` | 单元测试 |

---

## 9. 实施阶段建议

### 阶段 1：基础检查（优先级高）

1. 实现 `MisakaUpdateService.check_for_update()`
2. 对接 GitHub Releases API
3. 完善设置页 Misaka 更新区块 UI
4. 支持手动「检查更新」与「立即更新」（frozen 模式仅下载 + 打开）

### 阶段 2：体验优化

1. 启动时静默检查（可配置）
2. 有更新时在聊天页顶部显示横幅（类似 Claude Code 更新）
3. 可选：发布说明弹窗

### 阶段 3：发布流程集成

1. CI/CD 中自动创建 GitHub Release

2. 发布时上传：
   - Windows: `Misaka-{version}-win64.zip` 或 `.exe`
   - macOS: `Misaka-{version}-macos.dmg` 或 `.app.zip`
   - Linux: `Misaka-{version}-linux.tar.gz`

3. 版本号与 `tag_name` 保持一致（如 `v0.1.1`）

---

## 10. 配置与发布清单

### 10.1 需确定的配置

- **GitHub 仓库**：`owner/repo`，用于 API 请求
- **API 限流**：未认证请求约 60 次/小时，可考虑 `GITHUB_TOKEN` 环境变量
- **资产命名规范**：便于 `_get_asset_for_platform` 匹配，例如：
  - `Misaka-0.1.1-win64.zip`
  - `Misaka-0.1.1-macos-arm64.dmg`
  - `Misaka-0.1.1-linux-x64.tar.gz`

### 10.2 i18n 键补充

```json
{
  "misaka_update": "Misaka 更新",
  "misaka_update_desc": "检查 Misaka 应用更新",
  "misaka_version": "当前版本",
  "misaka_latest_version": "最新版本",
  "misaka_update_available": "有更新",
  "misaka_up_to_date": "已是最新",
  "misaka_update_now": "立即更新",
  "misaka_downloading": "正在下载...",
  "misaka_download_complete": "下载完成，请打开安装包完成更新",
  "misaka_update_failed": "更新失败",
  "misaka_check_failed": "检查失败",
  "misaka_retry": "重试",
  "update_not_configured": "更新服务器尚未配置"
}
```

---

## 11. 总结

Misaka 的在线更新功能可基于 **GitHub Releases API** 实现，无需自建服务器。核心要点：

1. **服务拆分**：新增 `MisakaUpdateService`，与 Claude Code 的 `UpdateCheckService` 分离
2. **双模式**：按 `sys.frozen` 区分 PyInstaller 与 pip 两种安装方式
3. **frozen 模式**：下载安装包并引导用户安装，不自动覆盖
4. **pip 模式**：执行 `pip install -U misaka` 实现自动升级
5. **UI 集成**：在设置页完善 Misaka 更新区块，并可选在聊天页顶部显示更新横幅
6. **发布流程**：在 CI 中自动创建 Release 并上传对应平台的安装包

按上述阶段实施，可逐步交付完整且可维护的更新能力。
