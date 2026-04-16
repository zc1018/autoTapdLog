---
name: tapd-log-creator
description: 通过 CDP 代理自动在 TAPD 上为 TASK 批量创建子需求（填 log）。当用户提到 "TAPD 填 log"、"批量创建子需求"、"自动填日志"、"给 task 建子任务" 或任何类似需求时，立即使用此 skill。支持自定义产品主R、处理人、规模、规划类型等参数。
compatibility:
  skills:
    - web-access
  notes: 依赖 web-access skill 提供的 CDP 代理（默认 http://localhost:3456）来控制浏览器操作 TAPD 页面。
---

# TAPD Log Creator

## 概述

此 skill 用于自动化在 TAPD 项目管理平台中为 TASK 类型工作项批量创建子需求（通常用于填写每日工作日志）。

核心能力：
1. 自动连接到本地 Chrome CDP 代理
2. 从 TAPD 列表页获取所有 TASK
3. 为每个 TASK 打开详情页，进入子需求 tab
4. 自动填写并提交子需求表单
5. **去重机制**：若该 TASK 下已存在相同处理人的子需求，则自动跳过

## 使用方式

### 步骤 1：确认环境依赖

- 用户必须在本地启动 Chrome 并开启远程调试（CDP 代理监听 `localhost:3456`）
- TAPD 页面必须已经登录，且列表页已应用好筛选条件（如产品主R=李思涵、状态=未结束等）
- 浏览器中必须有一个 attached 的 TAPD 标签页

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

1. **获取目标页面**：扫描 CDP 代理的 target 列表，找到当前 attached 的 TAPD 页面
2. **提取 TASK 列表**：导航到 `TAPD_LIST_URL`，提取所有 `TASK` 类型的工作项 ID
3. **循环处理每个 TASK**：
   - 导航到 TASK 详情页
   - 点击「子需求」tab
   - 检查是否已有处理人为 `TAPD_LOG_OWNER` 的子需求
   - 若有，跳过；若无，继续
   - 点击「快速添加子需求」
   - **不修改标题**（保留默认继承的父需求标题）
   - 填写：规划类型、规模、处理人
   - 点击「创建」
   - 等待 3 秒，检查弹窗是否关闭以确认成功
4. **输出统计**：成功数 / 跳过数 / 失败数

## 技术实现要点

- 通过 CDP 代理的 `/eval` 端点执行 JavaScript 来操作页面 DOM
- 通过 CDP 代理的 `/navigate` 端点控制页面跳转
- 表单填写通过直接修改 Vue 组件 `card-content` 的 `form` 对象实现，绕过复杂的 UI 事件链
- 子需求列表查询通过页面内 `fetch("/api/stories?...")` 完成

## 常见问题

**Q: 提示 "未找到 attached 的 TAPD 页面"**
A: 确保 Chrome 远程调试已开启，且浏览器中至少有一个打开并处于前台的 TAPD 标签页。

**Q: 弹窗未关闭，创建失败**
A: 可能是网络延迟或页面元素未加载完成。可尝试增大脚本中的 `time.sleep()` 等待时间。

**Q: 只想测试一个 TASK**
A: 可以临时修改 `tapd_create_log.py`，在 `for idx, task in enumerate(tasks, 1):` 循环中加入 `break` 或只取 `tasks[:1]`。
