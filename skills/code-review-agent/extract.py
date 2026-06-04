#!/usr/bin/env python3
"""
代码审查 Agent - 仓库数据提取器
克隆仓库 → 提取本周 commits → 按开发者分组 → 输出结构化数据
供多模型子 agent 审查使用
"""
import subprocess, json, os, sys, tempfile
from datetime import datetime, timedelta
from collections import defaultdict

_TMPDIR = tempfile.gettempdir()
HOME = os.path.expanduser("~")

CONFIG = {
    "repos": [
        {"name": "monorepo", "url": "https://github.com/lynaimining/lynai-miningclawd-monorepo", "local": os.path.join(_TMPDIR, "code-review-mono")},
        {"name": "data-pipeline", "url": "https://github.com/lynaimining/lynai-miningclawd-data-pipeline", "local": os.path.join(_TMPDIR, "code-review-data")},
    ],
    "developers": {
        "夏童": {"github": ["xiatong"], "alias": ["acxt", "cxt", "陈夏彤"]},
        "薛娴": {"github": ["xuexiansc-bit"], "alias": ["xian"]},
        "林素雅": {"github": ["Linsuya"], "alias": ["KIP", "素雅"]},
        "慧怡": {"github": ["huiyi"], "alias": ["冬末", "杜慧仪", "杜慧怡"]},
    }
}

def run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)

def clone_repos():
    for repo in CONFIG["repos"]:
        if os.path.exists(repo["local"]):
            print(f"📦 更新 {repo['name']}...")
            run(f"git fetch --all --unshallow 2>/dev/null; git pull --all", cwd=repo["local"])
        else:
            print(f"📦 克隆 {repo['name']}...")
            run(f"git clone {repo['url']} {repo['local']}")

def get_commits(repo_path, since, until):
    """获取指定时间范围内的 commits"""
    fmt = "%H|%ad|%an|%ae|%s"
    cmd = f'git log --all --since="{since}" --until="{until}" --format="{fmt}" --date=short --no-merges'
    result = run(cmd, cwd=repo_path)
    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line: continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            commits.append({
                "hash": parts[0],
                "date": parts[1],
                "author": parts[2],
                "email": parts[3],
                "message": parts[4]
            })
    return commits

def get_diff(repo_path, commit_hash):
    """获取单个 commit 的 diff"""
    result = run(f"git diff {commit_hash}^..{commit_hash} --stat", cwd=repo_path)
    return result.stdout

def get_changed_files(repo_path, commit_hash):
    """获取变更文件列表"""
    result = run(f"git diff-tree --no-commit-id --name-only -r {commit_hash}", cwd=repo_path)
    return [f for f in result.stdout.strip().split('\n') if f]

def match_developer(author_name):
    """根据 git author 匹配开发者"""
    for dev_name, dev_info in CONFIG["developers"].items():
        all_names = dev_info["github"] + dev_info["alias"]
        for name in all_names:
            if name.lower() in author_name.lower():
                return dev_name
    return author_name  # unknown

def main():
    # 默认周期：本周一至今天
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    since = monday.strftime("%Y-%m-%d")
    until = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    
    if len(sys.argv) >= 3:
        since, until = sys.argv[1], sys.argv[2]
    
    print(f"🔍 审查周期: {since} → {until}")
    
    # Step 1: 克隆/更新仓库
    clone_repos()
    
    # Step 2: 提取所有 commits
    all_commits = []
    for repo in CONFIG["repos"]:
        commits = get_commits(repo["local"], since, until)
        for c in commits:
            c["repo"] = repo["name"]
        all_commits.extend(commits)
        print(f"  {repo['name']}: {len(commits)} commits")
    
    # Step 3: 按开发者分组
    by_developer = defaultdict(list)
    for c in all_commits:
        dev = match_developer(c["author"])
        by_developer[dev].append(c)
    
    # Step 4: 生成结构化输出
    result = {
        "period": {"since": since, "until": until},
        "summary": {
            "total_commits": len(all_commits),
            "total_developers": len(by_developer),
            "repos": {r["name"]: len([c for c in all_commits if c["repo"]==r["name"]]) for r in CONFIG["repos"]}
        },
        "developers": {}
    }
    
    for dev_name, commits in sorted(by_developer.items()):
        print(f"\n  👤 {dev_name}: {len(commits)} commits")
        
        dev_data = {
            "commit_count": len(commits),
            "commits": [],
            "changed_files": [],
            "repos_touched": set()
        }
        
        for c in commits[:20]:  # 最多20个commit详情
            print(f"    {c['hash'][:7]} {c['date']} {c['message'][:80]}")
            files = get_changed_files(CONFIG["repos"][0]["local"] if c["repo"]=="monorepo" else CONFIG["repos"][1]["local"], c["hash"])
            dev_data["commits"].append({
                "hash": c["hash"][:7],
                "date": c["date"],
                "message": c["message"],
                "repo": c["repo"],
                "files": files
            })
            dev_data["changed_files"].extend(files)
            dev_data["repos_touched"].add(c["repo"])
        
        dev_data["repos_touched"] = list(dev_data["repos_touched"])
        dev_data["changed_files"] = list(set(dev_data["changed_files"]))[:50]
        result["developers"][dev_name] = dev_data
    
    # 输出 JSON
    output_path = os.path.join(_TMPDIR, "code-review-summary.json")
    with open(output_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 审查数据已导出: {output_path}")
    print(f"   总计 {len(all_commits)} commits / {len(by_developer)} 位开发者")

if __name__ == "__main__":
    main()
