#!/usr/bin/env python3
"""
TAPD 批量创建子需求（填 log）脚本 — 混合架构版
- 读操作（列表/去重）通过 opencli 完成
- 写操作（创建子需求）通过 CDP 代理控制浏览器完成
"""
import json
import subprocess
import time
import urllib.request
import urllib.parse
import sys
import os

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "progress.json")


def load_config():
    """从环境变量加载配置"""
    return {
        "proxy": os.environ.get("TAPD_PROXY", "http://localhost:3456"),
        "workspace_id": os.environ.get("TAPD_WORKSPACE_ID", "49782315"),
        "product_owner": os.environ.get("TAPD_PRODUCT_OWNER", "李思涵"),
        "log_owner": os.environ.get("TAPD_LOG_OWNER", "郭梁"),
        "log_size": os.environ.get("TAPD_LOG_SIZE", "11"),
        "log_plan_type": os.environ.get("TAPD_LOG_PLAN_TYPE", "迭代常规"),
        "list_url": os.environ.get("TAPD_LIST_URL", ""),
    }


def load_progress():
    """加载已处理的 task_id 进度"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"completed": [], "skipped": []}
    return {"completed": [], "skipped": []}


def save_progress(progress):
    """持久化进度到文件"""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def _run_opencli(site, name, *args):
    """运行 opencli 命令并解析 JSON 输出（过滤 stderr 警告）"""
    cmd = ["opencli", site, name] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    # opencli 可能把模块加载警告打到 stderr，但 stdout 通常就是一个纯 JSON
    stdout = result.stdout.strip()
    if stdout:
        try:
            return json.loads(stdout)
        except Exception:
            # 若 stdout 不是纯 JSON（比如混有其他日志），尝试提取第一个 { 或 [ 开始的完整块
            start = stdout.find("{")
            if start == -1:
                start = stdout.find("[")
            if start != -1:
                try:
                    return json.loads(stdout[start:])
                except Exception:
                    pass
    raise RuntimeError(f"opencli 返回无法解析的输出: {stdout[:500]}")


def get_task_ids(list_url, limit=200):
    """通过 opencli 从列表页获取所有 TASK"""
    data = _run_opencli(
        "tapd", "story-list",
        "--url", list_url,
        "--limit", str(limit),
        "-f", "json",
    )
    tasks = []
    for item in data.get("tasks", []):
        if item.get("type") == "TASK":
            tasks.append({
                "id": item.get("task_id", ""),
                "text": item.get("title", "") or item.get("summary", ""),
            })
    return {"count": len(tasks), "tasks": tasks}


def check_existing_child(task_url, owner):
    """通过 opencli 检查指定 TASK 是否已有某处理人的子需求"""
    try:
        data = _run_opencli("tapd", "task-detail", "--url", task_url, "-f", "json")
        owners = data.get("children_owners", [])
        return owner in owners
    except Exception as e:
        print(f"    ⚠️ opencli 去重检查失败: {e}，继续尝试创建")
        return False


def get_target_id(proxy):
    """获取当前 attached 的 TAPD 页面 target ID"""
    req = urllib.request.Request(f"{proxy}/targets", method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        targets = json.loads(resp.read())
    for t in targets:
        if t.get("attached") and "tapd.cn" in t.get("url", ""):
            return t["targetId"]
    raise RuntimeError("未找到 attached 的 TAPD 页面，请先在浏览器中打开 TAPD")


def eval_js(proxy, target, code, timeout=30):
    req = urllib.request.Request(
        f"{proxy}/eval?target={target}",
        data=code.encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        r = json.loads(resp.read())
        return r.get("value") if "value" in r else r


def navigate(proxy, target, url, wait=3):
    req = urllib.request.Request(
        f"{proxy}/navigate?target={target}&url={urllib.parse.quote(url, safe='')}",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            try:
                return json.loads(resp.read())
            except Exception:
                return {"ok": True}
    finally:
        if wait:
            time.sleep(wait)


def wait_for_element(proxy, target, selector, timeout=15, interval=0.5):
    """轮询等待 DOM 元素出现，代替固定 time.sleep"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        js = f"""
        (function() {{
            var el = document.querySelector({json.dumps(selector)});
            return JSON.stringify({{found: !!el}});
        }})()
        """
        result = eval_js(proxy, target, js)
        if isinstance(result, str):
            result = json.loads(result)
        if result.get("found"):
            return True
        time.sleep(interval)
    return False


def create_sub_requirement(proxy, target, workspace_id, task_id, config, max_retries=2):
    """为一个 TASK 创建子需求，支持重试和页面恢复"""
    for attempt in range(max_retries + 1):
        try:
            return _do_create_sub_requirement(proxy, target, workspace_id, task_id, config)
        except Exception as e:
            if attempt < max_retries:
                print(f"    ⚠️ 第{attempt+1}次尝试失败({e})，重新导航后重试...")
                navigate(
                    proxy, target,
                    f"https://www.tapd.cn/tapd_fe/{workspace_id}/story/detail/{task_id}?workitem_type_id=1149782315001000496",
                    wait=5,
                )
            else:
                raise


def _do_create_sub_requirement(proxy, target, workspace_id, task_id, config):
    """创建子需求的实际逻辑（仅 CDP 写操作）"""
    navigate(
        proxy,
        target,
        f"https://www.tapd.cn/tapd_fe/{workspace_id}/story/detail/{task_id}?workitem_type_id=1149782315001000496",
        wait=3,
    )

    # 等待页面加载完成
    if not wait_for_element(proxy, target, ".tab-container-item a.container-item-link", timeout=10):
        raise RuntimeError("详情页加载超时，未找到 tab 元素")

    # 点击子需求 tab
    eval_js(proxy, target, """
    (function() {
        var tabs = document.querySelectorAll(".tab-container-item a.container-item-link");
        for (var i = 0; i < tabs.length; i++) {
            if (tabs[i].textContent.indexOf("子需求") !== -1) {
                tabs[i].click();
                return JSON.stringify({clicked: true, text: tabs[i].textContent.trim()});
            }
        }
        return JSON.stringify({clicked: false});
    })()
    """)

    # 等待子需求列表加载
    time.sleep(1)

    # 点击快速添加子需求
    eval_js(proxy, target, """
    (function() {
        var btns = document.querySelectorAll("button.agi-button");
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent.indexOf("快速添加子需求") !== -1) {
                btns[i].click();
                return JSON.stringify({clicked: true});
            }
        }
        return JSON.stringify({clicked: false});
    })()
    """)

    # 等待创建表单出现（轮询代替固定 sleep）
    if not wait_for_element(proxy, target, ".create-content", timeout=10):
        raise RuntimeError("创建表单未出现，快速添加子需求按钮可能未生效")

    # 填写表单（不修改标题）— 使用 json.dumps 防止 XSS/转义问题
    plan_type_js = json.dumps(config["log_plan_type"])
    size_js = json.dumps(config["log_size"])
    owner_js = json.dumps(config["log_owner"])

    eval_js(proxy, target, f"""
    (function() {{
        var cardContent = document.querySelector(".create-content").__vue__;
        cardContent.form.custom_field_11 = {plan_type_js};
        cardContent.form.size = {size_js};
        cardContent.form.owner = {owner_js};
        return JSON.stringify({{
            name: cardContent.form.name,
            custom_field_11: cardContent.form.custom_field_11,
            size: cardContent.form.size,
            owner: cardContent.form.owner
        }});
    }})()
    """)

    # 点击创建按钮
    eval_js(proxy, target, """
    (function() {
        var btns = document.querySelectorAll("button");
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent.trim() === "创建" && !btns[i].disabled) {
                btns[i].click();
                return JSON.stringify({clicked: true});
            }
        }
        return JSON.stringify({clicked: false});
    })()
    """)

    # 轮询等待弹窗关闭（代替固定 sleep 3秒）
    dialog_closed = False
    for _ in range(12):  # 最多等 6 秒
        time.sleep(0.5)
        result = eval_js(proxy, target, """
        (function() {
            var wrapper = document.querySelector('.create-workitem-dialog');
            if (!wrapper) return JSON.stringify({closed: true, reason: 'wrapper gone'});
            var style = window.getComputedStyle(wrapper);
            return JSON.stringify({closed: style.display === 'none'});
        })()
        """)
        if isinstance(result, str):
            result = json.loads(result)
        if result.get("closed"):
            dialog_closed = True
            break

    if dialog_closed:
        return {"success": True}
    else:
        return {"success": False, "reason": "dialog still open"}


def main():
    config = load_config()
    print("=" * 60)
    print("TAPD 批量创建子需求（填 log）")
    print("=" * 60)
    print(f"CDP 代理: {config['proxy']}")
    print(f"产品主R: {config['product_owner']}")
    print(f"处理人: {config['log_owner']}")
    print(f"规模: {config['log_size']}")
    print(f"规划类型: {config['log_plan_type']}")

    if not config["list_url"]:
        print("\n❌ 错误: 未设置 TAPD_LIST_URL 环境变量")
        sys.exit(1)

    task_data = get_task_ids(config["list_url"])
    tasks = task_data.get("tasks", [])
    print(f"\n📋 共找到 {len(tasks)} 个 TASK")
    for i, t in enumerate(tasks[:5]):
        print(f"  [{i+1}] {t['id']} - {t['text'][:50]}")
    if len(tasks) > 5:
        print(f"  ... 还有 {len(tasks) - 5} 个")

    # 加载进度，跳过已完成的
    progress = load_progress()
    done_set = set(progress.get("completed", []) + progress.get("skipped", []))

    # 预检查：批量用 opencli 过滤已存在的，减少 CDP 依赖
    print("\n🔍 正在用 opencli 预检查子需求去重...")
    tasks_to_create = []
    for task in tasks:
        task_id = task["id"]
        if task_id in done_set:
            continue
        detail_url = f"https://www.tapd.cn/tapd_fe/{config['workspace_id']}/story/detail/{task_id}?workitem_type_id=1149782315001000496"
        if check_existing_child(detail_url, config["log_owner"]):
            progress["skipped"].append(task_id)
            save_progress(progress)
        else:
            tasks_to_create.append(task)

    print(f"⏭️ 已存在/已处理: {len(tasks) - len(tasks_to_create)} 个")
    print(f"📝 待创建: {len(tasks_to_create)} 个")

    if not tasks_to_create:
        print("\n✅ 没有需要创建的子需求")
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print("🧹 进度文件已清理")
        return

    # 只在真正需要创建时才连接 CDP
    target_id = get_target_id(config["proxy"])
    print(f"CDP 目标页面: {target_id}")

    success_count = 0
    skip_count = len(tasks) - len(tasks_to_create)
    fail_count = 0
    recover_count = sum(1 for t in tasks if t["id"] in done_set)

    for idx, task in enumerate(tasks_to_create, 1):
        task_id = task["id"]
        print(f"\n[{idx}/{len(tasks_to_create)}] 处理 {task_id} - {task['text'][:40]}")

        try:
            result = create_sub_requirement(
                config["proxy"], target_id, config["workspace_id"], task_id, config
            )
            if result.get("success"):
                success_count += 1
                progress["completed"].append(task_id)
                save_progress(progress)
                print(f"    ✅ 创建成功")
            else:
                fail_count += 1
                print(f"    ❌ 创建失败: {result}")
        except Exception as e:
            fail_count += 1
            print(f"    ❌ 异常: {e}")

    print(f"\n{'=' * 60}")
    print(f"✅ 成功: {success_count} | ⏭️ 跳过: {skip_count} (含恢复 {recover_count}) | ❌ 失败: {fail_count}")
    print("=" * 60)

    # 全部成功后清理进度文件
    if fail_count == 0 and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("🧹 进度文件已清理")


if __name__ == "__main__":
    main()
