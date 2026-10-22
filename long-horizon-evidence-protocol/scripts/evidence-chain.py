#!/usr/bin/env python3
"""evidence-chain.py — 长程任务证据链脚手架
用法:
  evidence-chain.py init <task-name>          # 建 evidence/<task>-<date>/ 目录
  evidence-chain.py round <dir> rN <topic>    # 记录一轮: json+stdout+stderr 三件套占位
  evidence-chain.py accept <dir> <json...>    # 生成 acceptance-summary.json (校验 all_exit_zero)
"""
import json, sys, datetime, pathlib

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "init":
        name = sys.argv[2]
        d = pathlib.Path("evidence") / f"{name}-{datetime.date.today():%Y%m%d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "README.md").write_text(f"# {name}\n\n轮次记录，失败轮保留不删除。\n")
        print(d)
    elif cmd == "round":
        d, rid, topic = pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
        base = d / f"{rid}-{topic}"
        for ext in (".json", ".stdout.log", ".stderr.log"):
            p = pathlib.Path(str(base) + ext)
            if not p.exists():
                p.write_text("")
        print(base)
    elif cmd == "accept":
        d = pathlib.Path(sys.argv[2])
        files = [pathlib.Path(f) for f in sys.argv[3:]]
        ok = all(json.load(open(f)).get("exit_code", 0) == 0 for f in files if f.suffix == ".json" and f.exists())
        summary = {"schema": "evidence-chain/1", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "rounds": [f.name for f in files], "all_exit_zero": ok,
                   "scope": "在此填写已验证范围与未验证项"}
        (d / "acceptance-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(d / "acceptance-summary.json", "all_exit_zero=", ok)

if __name__ == "__main__":
    main()
