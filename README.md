# autoTapdLog

自动化在 [TAPD](https://www.tapd.cn) 平台为 TASK 批量创建子需求（俗称"填 log"）。

通过 CDP（Chrome DevTools Protocol）代理控制浏览器，自动完成从任务列表获取、详情页跳转、表单填写到提交的全流程，并支持处理人去重，避免重复创建。

---

## 功能特性

- **批量自动填 log**：从 TAPD 列表页自动提取所有 TASK，逐个进入详情页创建子需求
- **智能去重**：若某 TASK 下已存在相同处理人的子需求，自动跳过
- **参数可配置**：产品主R、处理人、规模、规划类型等均支持通过环境变量自定义
- **保留默认标题**：不修改子需求标题，使用父需求默认继承的标题
- **依赖 Claude `web-access` skill**：复用其提供的 CDP 代理控制浏览器，自动携带登录态

---

## 前置准备

### 1. 安装并启用 `web-access` skill

本工具依赖 Claude Code 的 `web-access` skill 提供 CDP 代理服务（默认地址 `http://localhost:3456`）。

### 2. 启动 Chrome 远程调试

确保本地已启动 Chrome 并开启远程调试端口，例如：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=3456 \
  --user-data-dir=/tmp/chrome-dev-profile
```

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

1. **连接 CDP 代理**：扫描本地 CDP target 列表，找到当前 attached 的 TAPD 页面
2. **获取 TASK 列表**：导航到 `TAPD_LIST_URL`，提取页面中所有 `TASK` 类型的工作项 ID
3. **循环处理每个 TASK**：
   - 导航到 TASK 详情页
   - 点击「子需求」tab
   - 查询已有子需求，检查是否已存在相同处理人
   - 若已存在 → **跳过**；若不存在 → **继续创建**
   - 点击「快速添加子需求」
   - 不修改标题，填写：规划类型、规模、处理人
   - 点击「创建」，等待弹窗关闭确认成功
4. **输出统计**：打印成功数 / 跳过数 / 失败数

---

## 去重机制

脚本通过 TAPD 页面内 API 查询每个 TASK 的已有子需求：

```
/api/stories?workspace_id={workspace_id}&parent_id={story_id}&limit=200
```

如果返回的子需求列表中，`owner` 字段与 `TAPD_LOG_OWNER` 一致，则判定为已存在，自动跳过该 TASK，避免重复创建。

---

## 注意事项

1. **必须保持 TAPD 页面在前台**：CDP 代理需要 attached 的 target，请确保 TAPD 标签页是当前活动标签页
2. **网络延迟可能导致失败**：如果页面加载较慢，可以适当增大脚本中的 `time.sleep()` 等待时间
3. **仅处理 TASK 类型**：列表页中只提取标题包含 "TASK" 的工作项，其他类型（如 STORY）会被忽略
4. **先测试再批量运行**：建议先对单个 TASK 进行测试，确认环境无误后再批量执行所有任务
5. **不要关闭浏览器或切换标签页**：执行过程中请保持 Chrome 开启并停留在 TAPD 页面

---

## 技术实现

- **浏览器控制**：通过 CDP 代理的 `/eval` 和 `/navigate` 端点执行 JavaScript 与页面跳转
- **表单填写**：直接操作 Vue 组件 `card-content` 的 `form` 对象，绕过复杂的 UI 事件链：
  ```js
  var cardContent = document.querySelector(".create-content").__vue__;
  cardContent.form.custom_field_11 = "迭代常规";
  cardContent.form.size = "11";
  cardContent.form.owner = "郭梁";
  ```
- **子需求查询**：利用页面内 `fetch("/api/stories?...")` 自动携带当前登录态 Cookie

---

## 项目结构

```
autoTapdLog/
├── SKILL.md                     # Claude skill 元数据与使用说明
├── README.md                    # 本文件
└── scripts/
    └── tapd_create_log.py       # 核心自动化脚本
```

---

## 许可证

MIT
