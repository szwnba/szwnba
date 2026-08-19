#!/usr/bin/env python3
"""拉取 GitHub 账号下所有公开、非 Fork 的仓库，刷新 README.md 中的项目列表。

README.md 中用 <!-- projects:start --> 和 <!-- projects:end --> 标记
自动生成的区域，脚本只替换标记之间的内容，其余部分保持不变。
"""
import datetime
import json
import os
import re
import sys
import urllib.request

OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "szwnba")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
README_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "README.md")
START_MARKER = "<!-- projects:start -->"
END_MARKER = "<!-- projects:end -->"


def fetch_all_repos():
    repos, page = [], 1
    while True:
        url = (
            f"https://api.github.com/users/{OWNER}/repos"
            f"?type=owner&sort=pushed&per_page=100&page={page}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "update-projects-script",
        }
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
            batch = json.load(resp)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def cell(text):
    if text is None:
        return "—"
    cleaned = str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()
    return cleaned if cleaned else "—"


def build_section(repos):
    repos = [
        r for r in repos
        if not r.get("fork")
        and not r.get("private")
        and r.get("name", "").lower() != OWNER.lower()
    ]
    repos.sort(key=lambda r: (-(r.get("stargazers_count") or 0), r.get("pushed_at") or ""))

    if not repos:
        return "暂无公开项目。"

    today = datetime.date.today().isoformat()
    lines = [
        f"> 🔄 由 GitHub Actions 每周自动更新 · 共 {len(repos)} 个公开原创项目 · 更新时间：{today}",
        "",
        "| 项目 | 简介 |",
        "| :--- | :--- |",
    ]
    for r in repos:
        name = cell(r["name"])
        if r.get("archived"):
            name += " *(已归档)*"
        title = f"[**{name}**]({r['html_url']})"
        lines.append(f"| {title} | {cell(r.get('description'))} |")
    return "\n".join(lines)


def main():
    repos = fetch_all_repos()
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.S)
    if not pattern.search(content):
        sys.exit(f"错误：在 {README_PATH} 中未找到 {START_MARKER} / {END_MARKER} 标记")

    updated = pattern.sub(
        START_MARKER + "\n" + build_section(repos) + "\n" + END_MARKER,
        content,
    )
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)

    kept = sum(1 for r in repos if not r.get("fork") and not r.get("private"))
    print(f"获取到 {kept} 个仓库（含排除项共 {len(repos)} 个），README.md 已更新。")


if __name__ == "__main__":
    main()
