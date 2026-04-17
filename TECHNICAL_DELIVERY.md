# TAPD 批量创建子需求工具 — 技术交付文档

> **文档版本**: v1.1  
> **交付日期**: 2026-04-16  
> **仓库地址**: https://github.com/zc1018/autoTapdLog  
> **适用对象**: 开发、测试、运维及后续维护人员

---

## 1. 项目概述

### 1.1 背景与目标

在 TAPD 日常项目管理中，产品负责人需要为大量 TASK 重复创建子需求（Sub-Requirement）以填充工作日志。该过程涉及固定的表单字段（处理人、规模、规划类型等），手工操作效率极低且容易遗漏。

**本工具的目标是**：
- **自动化**：从指定 TASK 列表中批量提取目标 TASK；
- **智能化**：自动为每个 TASK 创建固定字段的子需求；
- **安全化**：在异常情况下具备自恢复能力，避免半途中断导致数据不一致。

### 1.2 核心特性

| 特性 | 说明 |
|------|------|
| **混合架构** | 读操作（列表/去重）通过 `opencli`，写操作（创建）通过 CDP |
| **Vue 组件注入** | 直接操作 TAPD 前端 Vue 组件的 `form` 对象，绕过复杂 DOM 事件模拟 |
| **断点续跑** | 通过 `progress.json` 记录已处理 TASK，中断后可从断点恢复 |
| **错误恢复** | 单 TASK 失败时自动刷新页面并重试，最大重试 2 次 |
| **安全注入** | 使用 `json.dumps()` 对表单值进行转义，防止特殊字符破坏 JS 注入 |
| **动态等待** | 用 DOM 元素轮询替代固定 `time.sleep`，提升执行效率与稳定性 |

---

## 2. 技术架构

### 2.1 整体架构图

```
┌─────────────────┐    opencli     ┌─────────────────┐
│   Python 脚本   │ ──────────────> │  tapd story-list│
│ tapd_create_log │ ──────────────> │ tapd task-detail│
│      .py        │                 │  (读操作)       │
└────────┬────────┘                 └─────────────────┘
         │
         │ 当需要去重/创建时
         │
         │    HTTP GET      ┌──────────────────┐
         │ ────────────────>│  CDP 代理服务    │
         │ <────────────────│ localhost:3456   │
         │   JSON 响应      │                  │
         │                  └────────┬─────────┘
         │                           │
         │                           │ WebSocket
         │                           │
         │                    ┌──────▼──────┐
         │                    │  Chrome     │
         │                    │  (已登录)   │
         │                    │  TAPD 页面  │
         │                    └─────────────┘
```

### 2.2 为什么采用混合架构（opencli + CDP）

| 方案 | 优点 | 缺点 |
|------|------|------|
| **纯 CDP** | 读写统一，控制力强 | 所有操作都依赖浏览器 target，去重阶段也需要频繁导航页面 |
| **纯 opencli** | 部署简单 | TAPD 的 Element UI 写表单对非真实用户交互敏感，提交不稳定 |
| **混合架构** | **opencli 负责读**（列表、去重），**CDP 负责写**（创建） | 需要同时维护 opencli YAML 和 CDP 逻辑，但稳定性和效率最佳 |

### 2.3 opencli 读取层

`opencli` 通过 YAML CLI 定义调用本地 Chrome，获取页面 DOM 数据：

- `tapd story-list`：导航到列表页，轮询等待表格加载，提取 `task_id` 和标题
- `tapd task-detail`：导航到详情页，点击「子需求」tab，提取已有子需求的处理人列表

两者均使用 `strategy: private` + `browser: true`，复用 Chrome 的 TAPD 登录态。

### 2.4 CDP 写入层

仅当确认某 TASK **需要去重后的创建** 时，Python 脚本才连接 CDP target，执行：

```javascript
document.querySelector(".create-content").__vue__.form
```

直接修改 Vue 组件内部状态，确保表单值被框架正确感知，后续点击"创建"按钮即可触发正常的校验和提交逻辑。

---

## 3. 环境依赖

### 3.1 系统要求

- **操作系统**: macOS / Linux / Windows (WSL)
- **Python**: 3.8+
- **浏览器**: Google Chrome / Chromium（建议最新稳定版）
- **opencli**: 已安装并配置 `~/.opencli/clis/tapd/` 下的 `story-list.yaml` 和 `task-detail.yaml`
- **网络**: 可访问 `https://www.tapd.cn`

### 3.2 外部依赖

| 依赖 | 说明 | 是否必需 |
|------|------|----------|
| opencli + TAPD YAML | 提供 `tapd story-list` / `task-detail` 命令 | 是 |
| CDP 代理 (`localhost:3456`) | 仅创建子需求时使用，提供 `/targets`, `/eval`, `/navigate` 端点 | 是 |
| TAPD 登录态 | Chrome 用户数据目录中需保持已登录状态 | 是 |
| `SKILL.md` | Claude Code Skill 集成定义（可选） | 否 |

### 3.3 Chrome 启动命令

首次配置时，使用持久化 profile 目录启动 Chrome：

```bash
mkdir -p ~/.chrome-tapd-profile

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=3456 \
  --user-data-dir="$HOME/.chrome-tapd-profile"
```

> ⚠️ **重要**: 不要使用 `/tmp` 作为 `--user-data-dir`。系统重启后 `/tmp` 会被清空，导致 TAPD 登录态丢失。

---

## 4. 项目结构

```
autoTapdLog/
├── README.md                      # 用户使用说明
├── SKILL.md                       # Claude Code Skill 定义
├── TECHNICAL_DELIVERY.md          # 本交付文档
└── scripts/
    └── tapd_create_log.py         # 主自动化脚本（混合架构）
    └── progress.json              # 执行进度（运行期自动生成）
```

---

## 5. 配置说明

所有配置通过**环境变量**注入，无需修改代码：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TAPD_PROXY` | `http://localhost:3456` | CDP 代理地址 |
| `TAPD_WORKSPACE_ID` | `49782315` | TAPD 工作空间 ID |
| `TAPD_PRODUCT_OWNER` | `李思涵` | 产品负责人（列表过滤用） |
| `TAPD_LOG_OWNER` | `郭梁` | 子需求处理人 |
| `TAPD_LOG_SIZE` | `11` | 子需求规模 |
| `TAPD_LOG_PLAN_TYPE` | `迭代常规` | 子需求规划类型 |
| `TAPD_LIST_URL` | *(必填)* | TASK 列表页完整 URL |

### 5.1 配置示例

```bash
export TAPD_LIST_URL="https://www.tapd.cn/tapd_fe/49782315/story/list?categoryId=0&..."
export TAPD_LOG_OWNER="郭梁"
export TAPD_LOG_SIZE="11"
export TAPD_LOG_PLAN_TYPE="迭代常规"

python3 scripts/tapd_create_log.py
```

---

## 6. 核心逻辑说明

### 6.1 主流程

```python
main()
  ├─ get_task_ids(list_url)          # opencli: 获取所有 TASK
  ├─ load_progress()                  # 读取 progress.json
  ├─ 批量去重检查（opencli task-detail）
  │   └─ 若已存在 → 标记 skipped
  ├─ get_target_id()                  # 仅在需要创建时连接 CDP
  └─ 遍历待创建 TASK
       └─ create_sub_requirement()    # CDP: 带重试机制的创建逻辑
            ├─ navigate()             # 跳转 TASK 详情页
            ├─ 点击"子需求" Tab
            ├─ 点击"快速添加子需求"
            ├─ wait_for_element()     # 轮询等待表单出现
            ├─ eval_js() 注入表单值  # owner / size / custom_field_11
            ├─ 点击"创建"按钮
            └─ 轮询等待弹窗关闭
            (失败时捕获异常，重试最多 2 次)
       └─ save_progress()             # 记录完成状态
```

### 6.2 关键函数详解

#### `get_task_ids(list_url, limit=200)`

通过 `subprocess.run` 调用 `opencli tapd story-list`，解析 stdout 中的 JSON：

```python
def get_task_ids(list_url, limit=200):
    data = _run_opencli("tapd", "story-list", "--url", list_url, "--limit", str(limit), "-f", "json")
    tasks = []
    for item in data.get("tasks", []):
        tasks.append({"id": item.get("task_id", ""), "text": item.get("title", "") or item.get("summary", "")})
    return {"count": data.get("total_found", 0), "tasks": tasks}
```

#### `check_existing_child(task_url, owner)`

通过 `opencli tapd task-detail` 获取子需求处理人列表，判断是否需要跳过：

```python
def check_existing_child(task_url, owner):
    data = _run_opencli("tapd", "task-detail", "--url", task_url, "-f", "json")
    owners = data.get("children_owners", [])
    return owner in owners
```

#### `create_sub_requirement(..., max_retries=2)`

封装了**错误恢复**层。当内部 `_do_create_sub_requirement()` 抛出异常时：
1. 捕获异常并打印告警；
2. 重新 `navigate()` 到 TASK 详情页；
3. 再次尝试创建；
4. 超过 `max_retries` 后抛出最终异常，外层记录为失败。

### 6.3 表单注入的安全处理

所有注入 JS 的字符串值均通过 `json.dumps()` 转义：

```python
plan_type_js = json.dumps(config["log_plan_type"])
owner_js = json.dumps(config["log_owner"])

js = f"""
(function() {{
    var f = document.querySelector(".create-content").__vue__.form;
    f.custom_field_11 = {plan_type_js};
    f.size = "11";
    f.owner = {owner_js};
}})()
"""
```

---

## 7. 容错与恢复机制

### 7.1 进度持久化（断点续跑）

- **文件位置**: `scripts/progress.json`
- **结构**:
  ```json
  {
    "completed": ["task_id_1", "task_id_2"],
    "skipped": ["task_id_3"]
  }
  ```
- **行为**:
  - 每成功/跳过一个 TASK，立即追加写入 `progress.json`；
  - 重启脚本时自动加载，已记录的 TASK 直接跳过；
  - 全部成功完成后，脚本自动删除 `progress.json`；
  - 如需强制重跑，手动删除 `progress.json` 即可。

### 7.2 单 TASK 异常恢复

| 场景 | 处理策略 |
|------|----------|
| 页面加载超时 | 重新导航到 TASK 详情页，重试 |
| 创建弹窗未出现 | 重试，再次点击"快速添加子需求" |
| 点击创建后弹窗未关闭 | 超时后返回失败，不记录进度，下次重跑会再次处理 |
| 网络抖动导致 CDP 请求失败 | 异常上抛，由 `max_retries` 控制重试 |
| opencli 去重检查失败 | 打印警告，继续尝试创建（保守策略） |

### 7.3 去重保护

在创建前，脚本通过 `opencli tapd task-detail` 检查每个 TASK 的子需求列表。如果已存在处理人相同的子需求，则标记为 `skipped`，避免重复填报。

---

## 8. 使用手册

### 8.1 首次使用

1. **安装 opencli** 并确保 `~/.opencli/clis/tapd/story-list.yaml` 和 `task-detail.yaml` 存在；
2. **启动 Chrome**（见第 3.3 节）；
3. **手动登录 TAPD**，进入目标项目；
4. **设置环境变量** `TAPD_LIST_URL`；
5. **运行脚本**：
   ```bash
   cd autoTapdLog
   python3 scripts/tapd_create_log.py
   ```

### 8.2 中断后继续

直接重新运行脚本即可，会自动读取 `progress.json` 跳过已处理的 TASK。

### 8.3 强制从头开始

```bash
rm scripts/progress.json
python3 scripts/tapd_create_log.py
```

---

## 9. 故障排查

### 9.1 "未找到 attached 的 TAPD 页面"

**原因**: Chrome 未开启远程调试，或当前没有打开 `tapd.cn` 标签页。  
**解决**:
- 确认 Chrome 以 `--remote-debugging-port=3456` 启动；
- 确认浏览器中至少有一个标签页打开了 TAPD；
- 检查 `http://localhost:3456/targets` 是否返回 JSON。

### 9.2 "opencli 返回无法解析的输出"

**原因**: opencli 的 stdout 被其他日志污染，或 TAPD YAML 定义文件损坏。  
**解决**:
- 手动运行 `opencli tapd story-list --url <url> -f json` 检查输出是否为纯 JSON；
- 检查 `~/.opencli/clis/tapd/*.yaml` 是否存在语法错误。

### 9.3 弹窗点了"创建"但没关闭

**原因**: 表单值虽然写入 Vue `form` 对象，但某些字段（如 Element UI Select）可能未触发响应式更新，导致前端校验未通过。  
**解决**:
- 这是当前架构的已知边界（Vue 直接注入 vs DOM 事件触发的差异）；
- 若频繁出现，建议在该 TASK 上暂停脚本，手工创建一次后删除 `progress.json` 再跑。

### 9.4 progress.json 损坏

**原因**: 脚本运行期间进程被强制杀死，文件写入不完整。  
**解决**:
- 手动删除 `progress.json` 后重跑；
- 或编辑 JSON 修复语法错误。

---

## 10. 维护与扩展

### 10.1 日常维护

- **定期检查** Chrome 的登录态是否过期（建议每月一次）；
- **验证 opencli TAPD 定义**：TAPD 前端改版后可能需要更新 YAML 中的 DOM 选择器；
- **关注 TAPD 前端更新**: 若 `.create-content`、`.create-workitem-dialog` 等 DOM class 变更，需同步更新 CDP 脚本中的选择器。

### 10.2 可扩展方向

| 方向 | 说明 |
|------|------|
| **多 owner 支持** | 将 `TAPD_LOG_OWNER` 扩展为列表，循环为多个处理人创建子需求 |
| **多规划类型** | 根据 TASK 标题关键词自动匹配不同的 `custom_field_11` |
| **钉钉/飞书通知** | 执行完成后推送成功/失败统计到 IM |
| **Headless 降级** | 若 TAPD 不再拦截，可迁移至 Playwright/Puppeteer 纯后台执行 |
| **日志持久化** | 将执行记录写入数据库或文件，便于审计和回溯 |

### 10.3 代码变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-04-16 | 交付 hardened 版本：JS 转义、错误恢复、轮询等待、进度持久化、profile 持久化 |
| v1.1 | 2026-04-16 | 升级为混合架构：读操作迁移至 opencli，CDP 仅用于创建子需求 |

---

## 附录：Claude Code Skill 集成

本仓库包含 `SKILL.md`，支持在 Claude Code 中通过自然语言触发：

```
用户: 创建 TAPD 子需求
Claude: 请确保 opencli 和 Chrome CDP 已就绪，然后设置 TAPD_LIST_URL 后运行脚本...
```

Skill 关键词：
- `tapd`
- `sub-requirement`
- `log`
- `batch`
