#!/usr/bin/env python3
"""
TAPD 批量创建子需求（填 log）脚本
通过 CDP 代理控制浏览器，自动为符合条件的 TASK 创建子需求
"""
import json
import time
import urllib.request
import urllib.parse
import sys
import os


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


def get_task_ids(proxy, target, list_url):
    """从列表页获取所有 TASK 类型的任务 ID"""
    navigate(proxy, target, list_url, wait=3)
    js = """
    (function() {
        var content = document.querySelector(".entity-list__content");
        if (!content) return JSON.stringify({error: "no content"});
        var rows = content.querySelectorAll("tr.row-item:not(.row-create-child)");
        var tasks = [];
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var id = row.getAttribute("id");
            var text = row.textContent.trim();
            if (text.indexOf("TASK") !== -1) {
                tasks.push({id: id, text: text.substring(0, 100)});
            }
        }
        return JSON.stringify({count: tasks.length, tasks: tasks});
    })()
    """
    result = eval_js(proxy, target, js)
    if isinstance(result, str):
        return json.loads(result)
    return result


def get_existing_children(proxy, target, workspace_id, story_id):
    """通过 TAPD 页面 API 获取已有子需求"""
    js = f"""
    (function() {{
        return fetch("/api/stories?workspace_id={workspace_id}&parent_id={story_id}&limit=200", {{
            method: "GET",
            credentials: "include"
        }}).then(function(r) {{ return r.text(); }})
        .then(function(text) {{
            try {{
                var data = JSON.parse(text);
                if (data && data.data) {{
                    var children = data.data.map(function(item) {{
                        return {{
                            id: item.id,
                            name: item.name,
                            owner: item.owner
                        }};
                    }});
                    return JSON.stringify(children);
                }}
            }} catch(e) {{
                return JSON.stringify({{error: e.message}});
            }}
            return JSON.stringify([]);
        }})
        .catch(function(e) {{ return JSON.stringify({{error: e.message}}); }});
    }})()
    """
    result = eval_js(proxy, target, js)
    if isinstance(result, str):
        try:
            return json.loads(result)
        except Exception:
            return {"error": result}
    return result


def create_sub_requirement(proxy, target, workspace_id, task_id, config):
    """为一个 TASK 创建子需求"""
    navigate(
        proxy,
        target,
        f"https://www.tapd.cn/tapd_fe/{workspace_id}/story/detail/{task_id}?workitem_type_id=1149782315001000496",
        wait=3,
    )

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
    time.sleep(2)

    # 获取已有子需求
    children = get_existing_children(proxy, target, workspace_id, task_id)
    if isinstance(children, list):
        owner_exists = any(c.get("owner") == config["log_owner"] for c in children)
        if owner_exists:
            return {"skipped": True, "reason": "already_exists"}
    else:
        print(f"    ⚠️ 获取子需求失败: {children}，继续尝试创建")

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
    time.sleep(2)

    # 填写表单（不修改标题）
    plan_type = config["log_plan_type"]
    size = config["log_size"]
    owner = config["log_owner"]

    eval_js(proxy, target, f"""
    (function() {{
        var cardContent = document.querySelector(".create-content").__vue__;
        cardContent.form.custom_field_11 = "{plan_type}";
        cardContent.form.size = "{size}";
        cardContent.form.owner = "{owner}";
        return JSON.stringify({{
            name: cardContent.form.name,
            custom_field_11: cardContent.form.custom_field_11,
            size: cardContent.form.size,
            owner: cardContent.form.owner
        }});
    }})()
    """)
    time.sleep(0.5)

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
    time.sleep(3)

    # 检查弹窗是否关闭
    dialog_closed = eval_js(proxy, target, """
    (function() {
        var dialog = document.querySelector(".create-workitem-dialog");
        return JSON.stringify({closed: !dialog || window.getComputedStyle(dialog).display === "none"});
    })()
    """)
    if isinstance(dialog_closed, str):
        dialog_closed = json.loads(dialog_closed)

    if dialog_closed.get("closed"):
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

    target_id = get_target_id(config["proxy"])
    print(f"目标页面: {target_id}")

    if not config["list_url"]:
        print("\n❌ 错误: 未设置 TAPD_LIST_URL 环境变量")
        sys.exit(1)

    task_data = get_task_ids(config["proxy"], target_id, config["list_url"])
    tasks = task_data.get("tasks", [])
    print(f"\n📋 共找到 {len(tasks)} 个 TASK")
    for i, t in enumerate(tasks[:5]):
        print(f"  [{i+1}] {t['id']} - {t['text'][:50]}")
    if len(tasks) > 5:
        print(f"  ... 还有 {len(tasks) - 5} 个")

    success_count = 0
    skip_count = 0
    fail_count = 0

    for idx, task in enumerate(tasks, 1):
        task_id = task["id"]
        print(f"\n[{idx}/{len(tasks)}] 处理 {task_id} - {task['text'][:40]}")
        try:
            result = create_sub_requirement(
                config["proxy"], target_id, config["workspace_id"], task_id, config
            )
            if result.get("skipped"):
                skip_count += 1
                print(f"    ⏭️ 已存在处理人为 {config['log_owner']} 的子需求，跳过")
            elif result.get("success"):
                success_count += 1
                print(f"    ✅ 创建成功")
            else:
                fail_count += 1
                print(f"    ❌ 创建失败: {result}")
        except Exception as e:
            fail_count += 1
            print(f"    ❌ 异常: {e}")

    print(f"\n{'=' * 60}")
    print(f"✅ 成功: {success_count} | ⏭️ 跳过: {skip_count} | ❌ 失败: {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
