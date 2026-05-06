# Learning Builder Skill 详解文档

---

## 1. 项目概述

`learning-builder` 是一个 Claude Code / Agent 技能（Skill），用于将用户模糊的学习需求转化为结构化的、有权威来源支撑的个性化学习教程包。它由 **Yao Team** 开发，当前版本 `0.1.0`，成熟度等级为 `production`（生产就绪）。

### 核心能力

| 能力 | 说明 |
|------|------|
| 需求澄清 | 通过简短对话明确学习目标、用户背景、时间预算等 |
| 权威研究 | 优先从官方文档、标准规范等一手来源收集资料 |
| 教程编纂 | 基于用户画像编写个性化教程，含练习和引用 |
| 多格式导出 | 从 markdown 源稿导出 `docx`、`html`、`pdf` |
| 网页扩展 | 教程确认后可选生成个性化学习网页 |

### 适用场景

- 想把某个主题做成系统化学习教程
- 希望教程内容有权威来源支撑
- 希望根据不同学习者背景定制内容深度和示例
- 希望最终得到 Word、PDF，或进一步扩展成网页

### 不适用场景

- 单次事实性问答
- 泛泛的资料汇总（不需要教程交付物）
- 纯粹把现成文档转成 PDF
- 只想做网页，不需要教程内容本身

---

## 2. 项目完整结构

```
skills/learning-builder/
├── SKILL.md                              # 技能入口：路由规则 + 完整工作流
├── manifest.json                         # 技能元数据清单
├── README.md                             # 英文使用说明
├── README.zh-CN.md                       # 中文使用说明
├── agents/
│   └── interface.yaml                    # Agent 接口适配配置（多平台兼容层）
├── input/
│   └── learner_profile_template.json     # 学习者画像 JSON 模板
├── references/
│   ├── authority-research.md             # 权威来源研究规则
│   ├── tutorial-assembly.md              # 教程结构契约
│   ├── export-pipeline.md                # 导出管道说明
│   └── webpage-extension.md              # 个性化网页扩展规则
├── reports/
│   ├── intent-dialogue.md                # 需求澄清对话指南
│   └── reference-scan.md                 # 设计参考扫描记录
├── scripts/
│   └── export_tutorial.py                # 教程导出脚本（markdown → docx/html/pdf）
├── evals/
│   └── trigger_cases.json                # 触发边界评估用例
└── templates/                            # （预留，当前为空）
```

---

## 3. 各文件详细说明

### 3.1 SKILL.md — 技能入口文件

**路径**: `SKILL.md`
**作用**: 这是技能的主入口。Claude Code 在路由判断时读取此文件的 frontmatter 来决定是否触发该技能。

**核心内容**:

| 区块 | 说明 |
|------|------|
| **Own The Following Job** | 定义技能的 5 项核心职责，明确处理范围 |
| **Inputs** | 列举技能期望接收的输入类型（主题、用户水平、时间预算等） |
| **Do Not Route Here** | 明确排除的场景，防止技能误触发 |
| **Default Workflow** | 7 步默认工作流，贯穿需求澄清到最终验证的完整链路 |
| **Output Contract** | 定义标准产出物集合（markdown 教程 + 来源附录 + 可选导出 + 可选网页） |
| **Validation Checklist** | 5 项验证检查点，确保交付物质量 |
| **Reference Map** | 指向各参考文档的索引，指导操作者何时读取什么文档 |

**frontmatter 字段**:
```yaml
name: learning-builder
description: Create personalized learning tutorials from a learner profile and authority-first research...
```

`description` 字段是关键路由依据 —— Claude Code 根据用户输入与此描述的匹配度决定是否激活技能。

---

### 3.2 manifest.json — 技能清单

**路径**: `manifest.json`

定义技能的元数据，用于技能注册中心和工厂组装。

**关键字段**:

| 字段 | 值 | 说明 |
|------|-----|------|
| `name` | `learning-builder` | 技能唯一标识 |
| `version` | `0.1.0` | 语义化版本 |
| `owner` | `Yao Team` | 维护团队 |
| `status` | `active` | 当前状态 |
| `maturity_tier` | `production` | 生产就绪级别 |
| `lifecycle_stage` | `active` | 生命周期阶段 |
| `context_budget_tier` | `production` | 上下文预算级别 |
| `review_cadence` | `monthly` | 审查节奏 |
| `category` | `education` | 分类 |
| `complexity_tier` | `complex` | 复杂度级别（非 trivial） |
| `target_platforms` | `["openai", "claude", "generic"]` | 目标平台，支持跨平台适配 |
| `factory_components` | `["references", "scripts", "evals", "input", "reports"]` | 参与技能工厂组装的组件列表 |

---

### 3.3 README.md / README.zh-CN.md — 使用说明

**路径**: `README.md`, `README.zh-CN.md`

面向用户的双语使用说明，包含：

- 技能功能简介
- 5 步主工作流
- 关键文件索引
- 脚本基础用法示例
- 产出物列表
- 注意事项（不是什么场景都适用）

---

### 3.4 agents/interface.yaml — Agent 接口适配层

**路径**: `agents/interface.yaml`

定义了该技能在不同 Agent 平台（OpenAI / Claude / Generic）上如何适配和激活。

**关键配置**:

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `display_name` | `Learning Builder` | Agent UI 中显示的名称 |
| `canonical_format` | `agent-skills` | 规范格式 |
| `adapter_targets` | `["openai", "claude", "generic"]` | 适配目标平台 |
| `activation.mode` | `manual` | 手动激活（非自动） |
| `execution.context` | `inline` | 内联执行（在 Agent 上下文中） |
| `trust.source_tier` | `local` | 本地源码级别信任 |
| `trust.remote_inline_execution` | `forbid` | 禁止远程内联执行 |
| `trust.remote_metadata_policy` | `allow-metadata-only` | 仅允许远程元数据 |

**平台降级策略**:
- OpenAI: `metadata-adapter`（元数据适配器）
- Claude: `neutral-source-plus-adapter`（中性源 + 适配器）
- Generic: `neutral-source`（中性源）

---

### 3.5 input/learner_profile_template.json — 学习者画像模板

**路径**: `input/learner_profile_template.json`

定义学习者的结构化 JSON 模板，是教程个性化的核心数据模型。

```json
{
  "topic": "",                    // 学习主题
  "learner_role": "",             // 学习者角色（如：PM、后端工程师）
  "current_level": "",            // 当前水平（如：beginner、intermediate）
  "target_outcome": "",           // 目标成果（具体可衡量的）
  "time_budget": "",              // 时间预算（如：3 hours、2 weeks）
  "language": "zh-CN",            // 语言偏好
  "preferred_tone": "",           // 语气偏好
  "preferred_examples": [],       // 示例领域偏好
  "must_cover": [],               // 必须覆盖的内容
  "out_of_scope": [],             // 排除范围
  "required_domains": [],         // 必须使用的来源域名
  "forbidden_domains": [],        // 禁止使用的来源域名
  "deliverables": ["markdown"],   // 交付物格式
  "want_personalized_webpage": false  // 是否需要个性化网页
}
```

**设计意图**: 在工作流第 2 步，意图澄清完成后填入此模板。缺失关键字段即视为阻塞项，不进入研究阶段。

---

### 3.6 references/authority-research.md — 权威研究规则

**路径**: `references/authority-research.md`

定义了来源选择的优先级体系和记录规范。

**5 级来源优先级**:
1. 官方产品或维护者文档
2. 标准组织/监管机构出版物/官方规范
3. 大学/研究实验室/政府出版物
4. 一手公司手册、变更日志、API 参考
5. 高质量二次解释材料（仅在前层不足时使用）

**研究规则要点**:
- 以学习目标为起点，而非随机搜索
- 首轮教程使用 3-7 个来源
- 记录每个来源的 URL、发布日期、信任理由
- 优先使用描述当前行为的来源
- 够用即止，不耗尽全网资料

**来源记录格式**: 每个来源需记录 title、URL、type、date、authority reason、borrow scope、limitation scope

**可信/需警惕的来源分类**: 明确将官方文档、RFC、维护者仓库等列为可靠来源；将 SEO 博客、AI 生成摘要、无维护者确认的论坛答案等列为需警惕的来源。

---

### 3.7 references/tutorial-assembly.md — 教程结构契约

**路径**: `references/tutorial-assembly.md`

定义了教程编写的结构规范和质量要求。

**10 个必备章节**:
| # | 章节 | 说明 |
|---|------|------|
| 1 | Learner Snapshot | 学习者快照 |
| 2 | Goal and Success Criteria | 目标和成功标准 |
| 3 | Prerequisites | 前置知识要求 |
| 4 | Concept Map | 概念地图 |
| 5 | Guided Core Lesson | 核心引导课程 |
| 6 | Worked Example or Walkthrough | 实操示例或演练 |
| 7 | Practice Tasks | 练习任务 |
| 8 | Common Mistakes | 常见错误 |
| 9 | Recommended Next Step | 推荐的下一步 |
| 10 | Source Appendix | 来源附录 |

**个性化原则**:
- 词汇量和深度匹配学习者水平
- 时间预算可视化呈现
- 示例关联到学习者的实际角色或项目
- 模糊目标转化为可衡量的完成指标
- 简化语言时保留来源准确性

**好的教程行为** vs **反模式**: 说明了何时解释"为什么"、如何区分必修/选修内容、避免从来源结构复制等教学原则。

---

### 3.8 references/export-pipeline.md — 导出管道

**路径**: `references/export-pipeline.md`

定义了从 markdown 源稿到多种发布格式的转换流程。

**核心原则**: markdown 为唯一可编辑的源，从源稿生成分发格式，不维护多份独立副本。

**当前环境配置**:
- `pandoc` 位于 `/opt/homebrew/bin/pandoc`
- 检测到 Google Chrome 和 Microsoft Edge 浏览器
- 未检测到 `soffice`、`xelatex`、`pdflatex`、`typst`

**推荐管道**:
1. 用 markdown 编写教程
2. `pandoc` → `docx`
3. `pandoc` → `html`
4. 无头浏览器打印 `html` → `pdf`

**设计理由**: pandoc 对 markdown→docx 转换可靠；本地浏览器可将 HTML 打印为 PDF 且无需 LaTeX 栈；同一份 HTML 可后续作为学习网页的种子。

**降级/升级路径**:
- 需要高级 Word 排版 → 路由到本地 `docx` skill
- 需要表单/合并等复杂 PDF → 路由到本地 `pdf` skill
- 需要可复用的前端页面族 → 使用 `skill-pageforge`

---

### 3.9 references/webpage-extension.md — 网页扩展

**路径**: `references/webpage-extension.md`

定义了如何将已确认的教程扩展为个性化学习网页。

**触发条件**: 仅在教学内容已被用户审批后启动，不可在教程阶段提前制作网页。

**最小页面区块**: 学习目标摘要、学习路径/模块列表、关键概念、实操示例、练习任务、来源链接、下一步行动号召。

**个性化信号**: 从学习者画像获取阅读深度、示例领域、节奏标签、语言语气、优先级高亮等参数。

**分支规则**: 根据用户需求分级处理 —— 单交付物时停于 markdown、需要页面原型时生成简单静态页、已有参考 HTML 时切换到 `skill-pageforge`。

---

### 3.10 scripts/export_tutorial.py — 导出脚本

**路径**: `scripts/export_tutorial.py`

这是一个约 150 行的 Python 3 命令行工具，实现了完整的 markdown → docx/html/pdf 导出流程。

**核心函数**:

| 函数 | 行号 | 功能 |
|------|------|------|
| `require_tool()` | 18 | 检查系统是否安装了指定工具（如 pandoc） |
| `find_pdf_browser()` | 25 | 自动搜索可用的 Chromium 系浏览器（Chrome/Edge/Brave/Chromium） |
| `run()` | 44 | 执行子进程命令 |
| `export_docx()` | 48 | 使用 pandoc 将 markdown 转换为 docx，支持参考文档和标题 |
| `export_html()` | 57 | 使用 pandoc 将 markdown 转换为独立 HTML，含嵌入式资源和目录 |
| `export_pdf()` | 80 | 使用无头 Chromium 浏览器将 HTML 打印为 PDF |
| `parse_args()` | 94 | 命令行参数解析 |
| `main()` | 112 | 主流程：验证输入 → 创建输出目录 → 按需调用各导出函数 |

**命令行用法**:
```bash
# 基础导出（生成 docx + html + pdf）
python3 scripts/export_tutorial.py tutorial.md out/

# 指定输出格式
python3 scripts/export_tutorial.py tutorial.md out/ --formats docx pdf

# 使用 Word 参考文档控制样式
python3 scripts/export_tutorial.py tutorial.md out/ --reference-doc templates/tutorial-reference.docx

# 指定标题和输出文件名
python3 scripts/export_tutorial.py tutorial.md out/ --title "My Tutorial" --basename my-tutorial

# 使用自定义 CSS
python3 scripts/export_tutorial.py tutorial.md out/ --css style.css --formats html
```

**依赖要求**:
- `pandoc`（必须安装并在 PATH 中）
- Google Chrome / Microsoft Edge / Brave / Chromium 之一（需要 PDF 导出时）
- Python 3.8+

---

### 3.11 reports/intent-dialogue.md — 需求澄清对话指南

**路径**: `reports/intent-dialogue.md`

定义了在深入研究和编写之前必须向用户提出的关键问题。

**5 个核心问题**:
1. 教程应该教授什么确切主题？
2. 学习者是谁？当前水平如何？
3. 学完后应该达到什么具体成果？
4. 有哪些时间、格式或来源约束？
5. 输出停在 markdown 还是需要 docx/pdf/网页？

**2 个补充问题**:
- 哪些示例对学习者来说会感到熟悉？
- 第一个版本应排除哪些内容？

**首轮假设**: 记录了技能的基本假设 —— 循环任务类型、真实输入、必需输出、排除项、推荐原型类型、首个评估目标。

---

### 3.12 reports/reference-scan.md — 参考扫描

**路径**: `reports/reference-scan.md`

记录了技能设计阶段的技术调研和借鉴决策。

**技能锚点**: 定义技能的 5 项构建目标。

**外部基准对象**: 调研了 4 个外部参考项目：
1. `qiaomu-epub-book-generator` — 完整的阅读制品工作流参考
2. Pandoc User's Guide — markdown→docx 转换的最佳实践
3. python-docx 文档 — Word 高级编辑的降级路径
4. ReportLab User Guide — PDF 确定性合成的替代方案

**本地适配约束**: 记录了本地技能库已有 `docx`/`pdf`/`skill-pageforge` 技能，当前环境有 pandoc 和 chromium，但没有 LaTeX 栈。

**借鉴计划**: 5 条关键设计决策 —— markdown 为单一源、核心围绕学习者需求而非格式转换、pandoc+Chromium 为 v1 默认管道、网页生成可选且后置、将格式专用工作路由到专用技能。

---

### 3.13 evals/trigger_cases.json — 触发边界评估

**路径**: `evals/trigger_cases.json`

定义了用于测试技能路由判断准确性的测试用例。

**结构**:
| 字段 | 值 | 说明 |
|------|-----|------|
| `recommended_threshold` | `0.33` | 推荐的路由相似度阈值 |
| `should_trigger` | 3 个用例 | 应该激活技能的典型请求 |
| `should_not_trigger` | 3 个用例 | 不应该激活技能的请求 |
| `near_neighbor` | 3 个用例 | 边界模糊的请求（容易误判） |

**测试目的**: 当需要收紧路由边界时，这些用例可用于回归测试，确保技能在应该激活时激活、不应该激活时不激活。

---

## 4. 运作机制

### 4.1 技能激活机制

```
用户输入 → Claude Code 路由判断 → 匹配 SKILL.md frontmatter description → 激活技能
```

Claude Code 使用语义匹配来判断用户输入是否与技能的 `description` 字段匹配。当匹配度超过阈值时，技能被激活并加载 `SKILL.md` 中的完整工作流。

### 4.2 完整工作流

```
┌─────────────────────────────────────────────────────────────┐
│                    7 步默认工作流                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1          Step 2          Step 3          Step 4     │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ 需求澄清 │───→│ 画像填充 │───→│ 权威研究 │───→│ 教程编纂 │  │
│  │intent-   │    │learner_  │    │authority-│    │tutorial- │  │
│  │dialogue  │    │profile_  │    │research  │    │assembly  │  │
│  │          │    │template  │    │          │    │          │  │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘  │
│                                                             │
│  Step 5          Step 6          Step 7                     │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│  │ 格式导出 │───→│ 网页扩展 │───→│ 交付验证 │                 │
│  │export-   │    │webpage-  │    │validation│                │
│  │pipeline  │    │extension │    │checklist │                │
│  │          │    │ (可选)    │    │          │               │
│  └─────────┘    └─────────┘    └─────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Step 1: 需求澄清（Intent Dialogue）

读取 `reports/intent-dialogue.md`，向用户提出 5 个核心问题。只问会影响范围、来源选择或产出物形态的问题。一旦能用一句话清晰描述教程就停止提问。

#### Step 2: 画像填充（Profile Population）

将需求澄清的结果填入 `input/learner_profile_template.json`。如果关键字段（主题、水平、目标、时间预算）缺失，列出阻塞项，暂不进入研究阶段。

#### Step 3: 权威研究（Authority Research）

读取 `references/authority-research.md`，构建权威优先的来源列表。
- 从学习目标出发搜索，不是随机搜索
- 选取 3-7 个来源
- 记录 URL、发布日期和信任理由
- 优先选用描述当前行为的来源
- 发现矛盾时如实说明

#### Step 4: 教程编纂（Tutorial Assembly）

读取 `references/tutorial-assembly.md`，撰写 markdown 教程。
- 内容对齐学习者画像，而非来源顺序
- 包含全部 10 个必备章节
- 遵循个性化原则和好的教程行为准则
- 避免反模式

#### Step 5: 格式导出（Export）

如果用户请求了 docx/pdf 输出：
- 读取 `references/export-pipeline.md`
- 使用 `scripts/export_tutorial.py` 执行导出
- 用 markdown 作为唯一源稿，不维护多份独立副本

#### Step 6: 网页扩展（Webpage Extension）

仅当用户在教程审批后请求个性化网页时执行：
- 读取 `references/webpage-extension.md`
- 网页是教程包的扩展，不是替代品
- 根据复杂度分级处理（静态页 / skill-pageforge）

#### Step 7: 交付验证（Validation）

检查 5 项质量标准：
1. 学习目标明确
2. 关键主张有权威来源引用支撑
3. 练习和后续步骤匹配学习者水平
4. 请求的导出文件实际产出
5. 网页制作没有替代核心教程交付物

---

### 4.3 模块协作关系

```
SKILL.md（调度中心）
  │
  ├─→ reports/intent-dialogue.md      ← 对话脚本
  ├─→ input/learner_profile_template.json ← 数据模型
  ├─→ references/authority-research.md ← 研究规则
  ├─→ references/tutorial-assembly.md ← 写作规则
  ├─→ references/export-pipeline.md   ← 导出规则
  ├─→ scripts/export_tutorial.py      ← 导出执行
  ├─→ references/webpage-extension.md ← 网页扩展规则
  └─→ evals/trigger_cases.json        ← 路由测试

agents/interface.yaml                  ← 跨平台适配层
manifest.json                          ← 技能注册元数据
```

---

## 5. 使用指南

### 5.1 触发方式

用户在 Claude Code 中直接描述学习需求即可触发：

> "帮我做一个 Kubernetes 入门教程，我是后端开发，有一定 Docker 基础，希望 4 小时内学完核心概念，导出 docx 和 pdf。"

Claude Code 会自动匹配到 `learning-builder` skill。

### 5.2 使用流程

1. **发起请求** — 告诉 Claude 你想学习什么
2. **回答追问** — Claude 会问 2-5 个澄清问题（主题、水平、目标、时间、格式）
3. **等待研究** — Claude 从权威来源收集资料（约需几个搜索回合）
4. **审阅教程** — Claude 生成 markdown 教程后进行审阅
5. **获取导出** — 如需 Word/PDF，Claude 运行导出脚本生成文件
6. **可选网页** — 教程确认后，可要求生成个性化学习网页

### 5.3 导出脚本独立使用

如果已有 markdown 教程，可独立运行导出脚本：

```bash
# 导出全部三种格式
python3 skills/learning-builder/scripts/export_tutorial.py tutorial.md out/

# 仅导出 docx
python3 skills/learning-builder/scripts/export_tutorial.py tutorial.md out/ --formats docx

# 使用参考文档
python3 skills/learning-builder/scripts/export_tutorial.py tutorial.md out/ \
  --reference-doc templates/tutorial-reference.docx

# 禁用目录
python3 skills/learning-builder/scripts/export_tutorial.py tutorial.md out/ --toc=false
```

### 5.4 环境要求

| 组件 | 用途 | 必需 |
|------|------|------|
| `pandoc` | markdown → docx/html 转换 | 是（导出时） |
| Chromium 系浏览器 | HTML → PDF 打印 | 是（PDF 导出时） |
| Python 3.8+ | 运行导出脚本 | 是（导出时） |

---

## 6. 设计原则与架构决策

### 6.1 权威优先原则

来源质量直接决定教程质量。技能硬性要求优先使用官方文档、标准规范等一手来源，明确将 SEO 博客、AI 生成摘要等标记为需要额外审视。

### 6.2 单一源原则

markdown 是唯一可编辑的源稿。`docx`、`html`、`pdf` 都从 markdown 生成，不维护多份独立副本。这意味着修改内容只需改一处。

### 6.3 个性化优先于信息量

教程从学习者画像出发编写（先理解"谁在学"），而非从搜索结果出发（"找到了什么就写什么"）。同一主题、不同学习者的教程内容应显著不同。

### 6.4 技能协作而非重复造轮

本技能不重复实现 `docx`、`pdf`、`skill-pageforge` 的全部能力，而是在需要高级功能时将对应阶段路由到这些专用技能。这符合"编制而非替代"的架构原则。

### 6.5 验证后交付

工作流末尾有结构化的验证检查表，确保每个交付物都经检查后才算完成。

---

## 7. 扩展点

### 7.1 模板系统

`templates/` 目录当前为空，可放入 `tutorial-reference.docx` 等参考文档，用于控制 pandoc 导出 Word 文档的样式。

### 7.2 导出升级路径

- **Word 深度编辑** → 路由到本地 `docx` skill
- **PDF 复杂排版** → 路由到本地 `pdf` skill
- **网页家族** → 路由到 `skill-pageforge`

### 7.3 评估用例扩展

`evals/trigger_cases.json` 可扩充更多测试用例以提高路由准确性。当前阈值 `0.33` 可根据实际使用数据调整。

---

## 8. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.1.0 | 2026-04-09 | 初始版本，支持 markdown 教程生成 + docx/html/pdf 导出 + 可选网页扩展 |

---

> 生成时间: 2026-05-02
> 技能版本: v0.1.0
> 维护团队: Yao Team
