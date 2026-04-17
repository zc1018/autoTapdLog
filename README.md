# autoTapdLog

自动化在 [TAPD](https://www.tapd.cn) 平台为 TASK 批量创建子需求（俗称"填 log"）。

采用**混合架构**：
- **读取**通过 `opencli` 完成（获取 TASK 列表、去重检查）
- **写入**通过 CDP（Chrome DevTools Protocol）代理控制浏览器完成（创建子需求表单填写与提交）

---

## 功能特性

- **批量自动填 log**：从 TAPD 列表页自动提取所有 TASK，逐个创建子需求
- **智能去重**：若某 TASK 下已存在相同处理人的子需求，自动跳过，避免重复操作
- **去重与创建分离**：大量去重工作通过 `opencli` 免 CDP 完成，只有必要时才连接浏览器
- **参数可配置**：产品主R、处理人、规模、规划类型均支持通过环境变量自定义
- **保留默认标题**：不修改子需求标题，使用父需求默认继承的标题
- **断点续跑**：通过 `progress.json` 记录已处理的 TASK，中断后可从断点恢复

---

## 前置准备

### 1. 安装 opencli

本工具的**读取层**依赖 `opencli`，需要安装并配置好 TAPD 站点定义。

确保 `~/.opencli/clis/tapd/` 目录下包含：
- `story-list.yaml` — 用于获取 TASK 列表
- `task-detail.yaml` — 用于获取单个 TASK 的子需求处理人

验证方式：
```bash
opencli tapd story-list --url "你的TAPD列表URL" --limit 5 -f json
```

### 2. 启动 Chrome 远程调试（用于创建操作）

确保本地已启动 Chrome 并开启远程调试端口：

```bash
# 使用持久化目录保存登录态（推荐），避免每次重新登录 TAPD
mkdir -p ~/.chrome-tapd-profile

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=3456 \
  --user-data-dir="$HOME/.chrome-tapd-profile"
```

> ⚠️ **注意**：不要使用 `/tmp` 目录，重启后登录态会丢失。首次启动后需手动登录 TAPD 一次，后续会自动保持登录状态。

### 3. 登录 TAPD 并准备好筛选页

- 在浏览器中登录 TAPD
- 打开 TASK 列表页，手动设置好筛选条件（如：产品主R=李思涵、状态=所有未结束状态）
- 确保该 TAPD 标签页处于前台（attached 状态）
- 复制当前列表页的完整 URL，作为 `TAPD_LIST_URL`

---

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/zc1018/autoTapdLog.git
cd autoTapdLog

# 配置环境变量
export TAPD_LIST_URL="https://www.tapd.cn/tapd_fe/49782315/story/list?..."
export TAPD_LOG_OWNER="郭梁"
export TAPD_LOG_SIZE="11"
export TAPD_LOG_PLAN_TYPE="迭代常规"

# 执行脚本
python3 scripts/tapd_create_log.py
```

---

## 环境变量说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `TAPD_PROXY` | CDP 代理地址 | `http://localhost:3456` |
| `TAPD_WORKSPACE_ID` | TAPD 工作空间 ID | `49782315` |
| `TAPD_LIST_URL` | 已筛选好的 TASK 列表页 URL | **必填** |
| `TAPD_PRODUCT_OWNER` | 产品主R（用于日志显示） | `李思涵` |
| `TAPD_LOG_OWNER` | 子需求处理人 | `郭梁` |
| `TAPD_LOG_SIZE` | 子需求规模 | `11` |
| `TAPD_LOG_PLAN_TYPE` | 规划类型 | `迭代常规` |

### 自定义示例

```bash
export TAPD_LIST_URL="https://www.tapd.cn/tapd_fe/49782315/story/list?..."
export TAPD_PRODUCT_OWNER="张三"
export TAPD_LOG_OWNER="李四"
export TAPD_LOG_SIZE="8"
export TAPD_LOG_PLAN_TYPE="技术债务"

python3 scripts/tapd_create_log.py
```

---

## 工作流程

1. **获取 TASK 列表**：通过 `opencli tapd story-list` 提取 `TAPD_LIST_URL` 中的所有 TASK
2. **批量去重检查**：通过 `opencli tapd task-detail` 检查每个 TASK 是否已有目标处理人的子需求
3. **连接 CDP**：只有当存在需要创建的 TASK 时，才扫描 CDP target 连接浏览器
4. **循环创建**：
   - 导航到 TASK 详情页
   - 点击「子需求」tab
   - 点击「快速添加子需求」
   - 不修改标题，填写：规划类型、规模、处理人
   - 点击「创建」，等待弹窗关闭确认成功
5. **输出统计**：打印成功数 / 跳过数 / 失败数

---

## 断点续跑

脚本自动记录处理进度到 `progress.json`。如果中途中断（网络断开、浏览器崩溃），重新运行时会自动跳过已处理成功的 TASK，从断点继续。

全部成功完成后，进度文件会自动清理。如需强制从头开始，手动删除 `progress.json` 即可。

---

## 注意事项

1. **opencli 需正常工作**：请确保 `opencli tapd story-list` 和 `opencli tapd task-detail` 命令能正常返回数据
2. **CDP 仅在创建时使用**：大量去重工作由 opencli 免 CDP 完成，只有真正需要创建的 TASK 才会连接浏览器
3. **网络延迟自适应**：脚本使用 DOM 元素轮询等待页面加载，网络慢时自动等待更长时间，无需手动调整
4. **仅处理 TASK 类型**：列表页中只提取标题包含 "TASK" 的工作项，其他类型（如 STORY）会被忽略
5. **先测试再批量运行**：建议先对单个 TASK 进行测试，确认环境无误后再批量执行所有任务
6. **不要关闭浏览器或切换标签页**：执行创建过程中请保持 Chrome 开启并停留在 TAPD 页面

---

## 技术实现

- **读取层**（opencli）：通过 YAML CLI 定义调用浏览器，获取 TASK 列表和子需求处理人列表
- **写入层**（CDP）：通过 CDP 代理的 `/eval` 端点执行 JavaScript，直接操作 Vue 组件 `card-content` 的 `form` 对象，绕过复杂的 UI 事件链：
  ```js
  var cardContent = document.querySelector(".create-content").__vue__;
  cardContent.form.custom_field_11 = "迭代常规";
  cardContent.form.size = "11";
  cardContent.form.owner = "郭梁";
  ```

---

## 项目结构

```
autoTapdLog/
├── SKILL.md                     # Claude skill 元数据与使用说明
├── README.md                    # 本文件
├── TECHNICAL_DELIVERY.md       # 技术交付文档
└── scripts/
    ├── tapd_create_log.py       # 核心自动化脚本（混合架构）
    └── progress.json            # 执行进度（运行期自动生成）
```

---

## 许可证

MIT
