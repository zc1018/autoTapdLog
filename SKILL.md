---
name: tapd-log-creator
description: 自动在 TAPD 上为 TASK 批量创建子需求（填 log）。当用户提到 "TAPD 填 log"、"批量创建子需求"、"自动填日志"、"给 task 建子任务" 或任何类似需求时，立即使用此 skill。支持自定义产品主R、处理人、规模、规划类型等参数。
compatibility:
  skills:
    - web-access
    - opencli
  notes: 
    - 读取操作（TASK 列表、去重检查）通过 opencli 完成
    - 创建操作依赖 web-access skill 提供的 CDP 代理（默认 http://localhost:3456）来控制浏览器操作 TAPD 页面
---

# TAPD Log Creator

## 概述

此 skill 用于自动化在 TAPD 项目管理平台中为 TASK 类型工作项批量创建子需求（通常用于填写每日工作日志）。

核心能力：
1. 通过 **opencli** 获取列表页中的所有 TASK，并预先检查每个 TASK 的子需求去重
2. 仅对真正需要创建的 TASK，通过 **CDP 代理** 自动填写表单并提交
3. 若该 TASK 下已存在相同处理人的子需求，则自动跳过，避免重复操作

## 使用方式

### 步骤 1：确认环境依赖

- **opencli** 已安装并配置好 `tapd` 站点定义（默认路径 `~/.opencli/clis/tapd/` 下应有 `story-list.yaml` 和 `task-detail.yaml`）
- 用户必须在本地启动 Chrome 并开启远程调试（CDP 代理监听 `localhost:3456`），**仅在需要创建时使用**
- 建议使用持久化 profile 目录（如 `~/.chrome-tapd-profile`），避免每次重启后登录态丢失
- TAPD 页面必须已经登录，且列表页已应用好筛选条件
- 浏览器中必须有一个 attached 的 TAPD 标签页（用于 CDP 创建操作）

### 步骤 2：配置参数

通过环境变量传入配置：

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `TAPD_PROXY` | CDP 代理地址 | `http://localhost:3456` |
| `TAPD_WORKSPACE_ID` | TAPD 工作空间 ID | `49782315` |
| `TAPD_LIST_URL` | 已筛选好的 TASK 列表页 URL | **必填** |
| `TAPD_PRODUCT_OWNER` | 产品主R（用于日志显示） | `李思涵` |
| `TAPD_LOG_OWNER` | 子需求处理人 | `郭梁` |
| `TAPD_LOG_SIZE` | 子需求规模 | `11` |
| `TAPD_LOG_PLAN_TYPE` | 规划类型 | `迭代常规` |

### 步骤 3：执行脚本

```bash
# 设置参数后运行
export TAPD_LIST_URL="https://www.tapd.cn/tapd_fe/49782315/story/list?..."
export TAPD_LOG_OWNER="郭梁"
export TAPD_LOG_SIZE="11"
export TAPD_LOG_PLAN_TYPE="迭代常规"

python3 scripts/tapd_create_log.py
```

## 工作流程

1. **获取 TASK 列表**：通过 `opencli tapd story-list` 提取 `TAPD_LIST_URL` 中的所有 TASK
2. **批量去重检查**：通过 `opencli tapd task-detail` 检查每个 TASK 是否已有目标处理人的子需求
3. **连接 CDP**：只有当存在需要创建的 TASK 时，才扫描 CDP target 连接浏览器
4. **循环创建**：
   - 导航到 TASK 详情页
   - 点击「快速添加子需求」
   - **不修改标题**（保留默认继承的父需求标题）
   - 填写：规划类型、规模、处理人
   - 点击「创建」
   - 等待弹窗关闭确认成功
5. **输出统计**：成功数 / 跳过数 / 失败数

## 技术实现要点

- **读取层**（opencli）：通过 YAML CLI 定义调用浏览器，获取 TASK 列表和子需求处理人列表
- **写入层**（CDP）：通过 CDP 代理的 `/eval` 端点执行 JavaScript，直接修改 Vue 组件 `card-content` 的 `form` 对象
- **无需一直挂载 CDP**：只有在需要创建时才会连接 target，大量去重工作在前期通过 opencli 完成

## 常见问题

**Q: 提示 "未找到 attached 的 TAPD 页面"**
A: 确保 Chrome 远程调试已开启，且浏览器中至少有一个打开并处于前台的 TAPD 标签页。

**Q: 弹窗未关闭，创建失败**
A: 可能是网络延迟或页面元素未加载完成。可尝试增大脚本中的轮询等待超时时间。

**Q: 只想测试一个 TASK**
A: 可以临时修改 `tapd_create_log.py`，在 `for idx, task in enumerate(tasks_to_create, 1):` 循环中加入 `break` 或只取 `tasks_to_create[:1]`。
