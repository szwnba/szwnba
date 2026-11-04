#!/usr/bin/env python3
"""项目指挥中心 · Project HQ 同步脚本

把 OWNER 的全部原创仓库（非 fork）同步进 GitHub Projects v2 板：
1. 每个仓库在 ISSUE_REPO 建一个带 `project-hq` 标签的跟踪 issue（幂等）；
2. 把跟踪 issue 加入项目板，并填充 领域 / 阶段 / 优先级 字段；
3. 已入板的条目按最近提交时间自动刷新「阶段」（永不覆盖 🟡 想法储备）。

环境变量：
  GH_TOKEN        必填
  PROJECT_ID      板的 node id（默认内置）
  OWNER / ISSUE_REPO  默认内置
仅用标准库。
"""
import json
import os
import sys
import time
import urllib.request

OWNER = os.environ.get("OWNER", "szwnba")
ISSUE_REPO = os.environ.get("ISSUE_REPO", "szwnba/szwnba")
PROJECT_ID = os.environ.get("PROJECT_ID", "PVT_kwHOAHfdCc4BqNk8")
TOKEN = os.environ.get("GH_TOKEN", "")

API = "https://api.github.com"

FIELD_DOMAIN = os.environ.get("FIELD_DOMAIN", "PVTSSF_lAHOAHfdCc4BqNk8zholsVk")
FIELD_STAGE = os.environ.get("FIELD_STAGE", "PVTSSF_lAHOAHfdCc4BqNk8zholsV0")
FIELD_PRIORITY = os.environ.get("FIELD_PRIORITY", "PVTSSF_lAHOAHfdCc4BqNk8zholsV4")

OPT_DOMAIN = {
    "内容自动化": os.environ.get("OPT_CA", "32acb1e7"),
    "Affiliate 出海": os.environ.get("OPT_AFF", "b8d991d7"),
    "知识管理": os.environ.get("OPT_KM", "6c2e1624"),
    "个人站点": os.environ.get("OPT_SITE", "c234b269"),
    "产品原型": os.environ.get("OPT_PROD", "e24b9efe"),
    "其他": os.environ.get("OPT_OTHER", "f3457ade"),
}
OPT_STAGE = {
    "active": os.environ.get("OPT_ACTIVE", "29dbf49a"),   # 🟢 活跃开发
    "maint": os.environ.get("OPT_MAINT", "6afeb261"),    # 🔵 维护运行
    "dormant": os.environ.get("OPT_DORM", "3ce14046"),   # ⚪ 休眠
    "idea": os.environ.get("OPT_IDEA", "c7983510"),      # 🟡 想法储备（手动）
}
OPT_PRIORITY = {
    "P0": os.environ.get("OPT_P0", "d61008ed"),
    "P1": os.environ.get("OPT_P1", "551f129d"),
    "P2": os.environ.get("OPT_P2", "9e5c7873"),
}

DOMAIN_BY_REPO = {
    # Affiliate 出海
    "affweb": "Affiliate 出海", "affpops": "Affiliate 出海", "affbook": "Affiliate 出海",
    # 内容自动化
    "wechat-article-pipeline": "内容自动化", "ai-blog": "内容自动化",
    "idea-radar": "内容自动化", "cyber-morning": "内容自动化", "aihot": "内容自动化",
    # 知识管理
    "obsidian": "知识管理", "we-article": "知识管理", "sediment-garden": "知识管理",
    "learn365": "知识管理", "study": "知识管理", "johnson-skills": "知识管理",
    "chinese-indie-makers": "知识管理",
    # 个人站点
    "szwnba.github.io": "个人站点", "szwnba": "个人站点",
    "github-showcase": "个人站点", "space": "个人站点",
    # 产品原型
    "mindnest": "产品原型", "coinlens": "产品原型",
    "DoitClone": "产品原型", "exercise-checkin": "产品原型",
}
PRIORITY_BY_REPO = {
    "affweb": "P0", "wechat-article-pipeline": "P0",
    "affpops": "P1", "idea-radar": "P1", "ai-blog": "P1",
    "obsidian": "P1", "we-article": "P1", "johnson-skills": "P1",
    "szwnba.github.io": "P1",
}
# 手动改过「想法储备」的仓库，别让自动阶段覆盖：脚本永不写 idea 选项。
STAGE_OVERRIDES = {"doit-data": "dormant"}  # 纯数据备份，不算活跃

LABELS = [
    ("project-hq", "BFD4F2", "项目指挥中心跟踪条目"),
    ("领域/内容自动化", "F9D0C4", ""),
    ("领域/Affiliate 出海", "F9C9D6", ""),
    ("领域/知识管理", "BFD4F2", ""),
    ("领域/个人站点", "D4C5F9", ""),
    ("领域/产品原型", "C2E0C6", ""),
    ("领域/其他", "EDEDED", ""),
]


def rest(method, path, payload=None, raw=False):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return json.loads(body) if body and not raw else body
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail}") from None


def gql(query, variables=None, retries=3):
    req = urllib.request.Request(
        API + "/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as r:
                out = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (502, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1)); continue
            raise RuntimeError(f"graphql -> {e.code}: {e.read().decode()[:300]}") from None
        if out.get("errors"):
            raise RuntimeError(f"graphql errors: {json.dumps(out['errors'], ensure_ascii=False)[:500]}")
        time.sleep(0.15)
        return out["data"]


def stage_of(pushed_at, name):
    if name in STAGE_OVERRIDES:
        return STAGE_OVERRIDES[name]
    days = (time.time() - time.mktime(time.strptime(pushed_at[:10], "%Y-%m-%d"))) / 86400
    if days <= 45:
        return "active"
    if days <= 180:
        return "maint"
    return "dormant"


def ensure_labels():
    existing = {x["name"] for x in rest("GET", f"/repos/{ISSUE_REPO}/labels?per_page=100")}
    for name, color, desc in LABELS:
        if name in existing:
            continue
        try:
            rest("POST", f"/repos/{ISSUE_REPO}/labels",
                 {"name": name, "color": color, "description": desc})
            print(f"label + {name}")
        except RuntimeError as e:
            if "422" not in e.args[0]:
                raise


def fetch_repos():
    q = """query($login:String!){user(login:$login){repositories(first:100,ownerAffiliations:OWNER,isFork:false){
      nodes{id name description primaryLanguage{name} stargazerCount pushedAt isArchived}}}}"""
    data = gql(q, {"login": OWNER})
    repos = [n for n in data["user"]["repositories"]["nodes"] if not n["isArchived"]]
    repos.sort(key=lambda n: n["pushedAt"], reverse=True)
    return repos


def fetch_tracking_issues():
    """返回 {仓库名: issue字典}。issue 标题约定：`📦 <repo> · <描述>`"""
    out, page = {}, 1
    while True:
        items = rest("GET", f"/repos/{ISSUE_REPO}/issues?labels=project-hq&state=all&per_page=100&page={page}")
        if not items:
            break
        for it in items:
            title = it["title"]
            if title.startswith("📦 "):
                name = title[2:].split(" ·")[0].strip()
                out[name] = it
        if len(items) < 100:
            break
        page += 1
    return out


def fetch_board_items():
    q = """query($id:ID!){node(id:$id){...on ProjectV2{items(first:100){nodes{
      id content{__typename ...on Issue{number repository{name}} ...on DraftIssue{title}}
      fieldValues(first:20){nodes{...on ProjectV2ItemFieldSingleSelectValue{
        name field{...on ProjectV2FieldCommon{id}}}}}}}}}}"""
    data = gql(q, {"id": PROJECT_ID})
    items = []
    for n in data["node"]["items"]["nodes"]:
        c = n["content"]
        entry = {"item_id": n["id"], "type": c.get("__typename"), "issue": None,
                 "fields": {}}
        if entry["type"] == "Issue":
            entry["issue"] = f"{c['repository']['name']}#{c['number']}"
        for fv in n["fieldValues"]["nodes"]:
            if "name" in fv and "field" in fv:
                entry["fields"][fv["field"]["id"]] = fv["name"]
        items.append(entry)
    return items


def issue_body(r):
    desc = r.get("description") or "（无描述）"
    lang = (r.get("primaryLanguage") or {}).get("name") or "-"
    return (
        "> [!NOTE]\n"
        "> 本 issue 由 **项目指挥中心 · Project HQ** 自动创建与维护，"
        "用于跟踪该项目的领域、阶段与优先级，请勿关闭。\n\n"
        f"**仓库**：[{OWNER}/{r['name']}](https://github.com/{OWNER}/{r['name']})  \n"
        f"**简介**：{desc}  \n"
        f"**主语言**：{lang}  \n"
        f"**Stars**：⭐ {r['stargazerCount']}  \n"
        f"**最近提交**：{r['pushedAt'][:10]}\n"
    )


def main():
    if not TOKEN:
        sys.exit("GH_TOKEN is required")
    ensure_labels()
    repos = fetch_repos()
    tracking = fetch_tracking_issues()
    board = fetch_board_items()
    by_issue = {e["issue"]: e for e in board if e["issue"]}

    created = added = updated = 0
    for r in repos:
        name = r["name"]
        domain = DOMAIN_BY_REPO.get(name, "其他")
        prio = PRIORITY_BY_REPO.get(name, "P2")
        stage = stage_of(r["pushedAt"], name)

        issue = tracking.get(name)
        if not issue:
            title = f"📦 {name} · {(r.get('description') or name)[:60]}"
            issue = rest("POST", f"/repos/{ISSUE_REPO}/issues", {
                "title": title, "body": issue_body(r),
                "labels": ["project-hq", f"领域/{domain}"],
            })
            created += 1
            print(f"issue + #{issue['number']} {name}")

        key = f"{name}#{issue['number']}"
        entry = by_issue.get(key)
        if entry:
            # 已入板：只刷新阶段，且不覆盖手动标记的 🟡 想法储备
            cur_stage = entry["fields"].get(FIELD_STAGE)
            if cur_stage == OPT_STAGE["idea"]:
                continue
            if cur_stage != OPT_STAGE[stage]:
                gql("""mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){
                  updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,
                    value:{singleSelectOptionId:$o}}){projectV2Item{id}}}""",
                    {"p": PROJECT_ID, "i": entry["item_id"], "f": FIELD_STAGE, "o": OPT_STAGE[stage]})
                updated += 1
                print(f"stage ~ {name} -> {stage}")
            continue

        # 新入板条目：加入并填充三个字段
        data = gql("""mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){
          item{id}}}""", {"p": PROJECT_ID, "c": issue["node_id"]})
        entry = {"item_id": data["addProjectV2ItemById"]["item"]["id"], "fields": {}}
        added += 1
        print(f"board + {name}")
        for fid, oid in ((FIELD_DOMAIN, OPT_DOMAIN[domain]),
                         (FIELD_STAGE, OPT_STAGE[stage]),
                         (FIELD_PRIORITY, OPT_PRIORITY[prio])):
            gql("""mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){
              updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,
                value:{singleSelectOptionId:$o}}){projectV2Item{id}}}""",
                {"p": PROJECT_ID, "i": entry["item_id"], "f": fid, "o": oid})
        print(f"fields + {name} [{domain}/{stage}/{prio}]")

    print(f"\n完成：新建 issue {created}，新入板 {added}，阶段刷新 {updated}，"
          f"板内共 {len(fetch_board_items())} 条")


if __name__ == "__main__":
    main()
