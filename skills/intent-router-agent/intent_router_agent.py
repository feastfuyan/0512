#!/usr/bin/env python3
"""
intent-router-agent — 自进化意图路由 Agent
通过 LLM 语义理解用户意图 + 自动学习纠错
"""
import json, os, sys, datetime, subprocess

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(AGENT_DIR, "routing-history.jsonl")
LEARNING_FILE = os.path.join(AGENT_DIR, "learning-data.json")
WORKSPACE = os.path.expanduser(os.environ.get("OPENCLAW_WORKSPACE", "~/.openclaw/workspace"))
ROUTER_SCRIPT = os.path.join(WORKSPACE, "scripts", "intent_router.py")
SKILL_INDEX = os.path.join(WORKSPACE, "skills", "openclaw-intent-router", "skill-registry.json")

os.makedirs(AGENT_DIR, exist_ok=True)

def load_learning():
    if os.path.exists(LEARNING_FILE):
        with open(LEARNING_FILE) as f:
            return json.load(f)
    return {"corrections": [], "stats": {"total_routes": 0, "correct": 0, "wrong": 0}}

def save_learning(data):
    with open(LEARNING_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def route_with_llm(query):
    """
    使用 LLM 进行意图路由
    若 LLM 不可用，回退到关键词路由
    """
    # Step 1: Try LLM-powered routing
    llm_result = try_llm_routing(query)
    if llm_result:
        return llm_result
    
    # Step 2: Fallback to keyword routing
    return route_with_keywords(query)

def try_llm_routing(query):
    """Use available LLM to classify intent"""
    # Read skill index
    if not os.path.exists(SKILL_INDEX):
        return None
    with open(SKILL_INDEX) as f:
        index = json.load(f)
    
    skills = index["skills"]
    
    # Build a condensed skill list for the LLM
    skill_lines = []
    for s in skills[:50]:  # Top 50
        triggers = ", ".join(s["triggers"][:3]) if s["triggers"] else "-"
        skill_lines.append(f"- {s['slug']}: {s['description'][:100]} [{triggers}]")
    
    # Load corrections for context
    learning = load_learning()
    corrections = learning.get("corrections", [])
    correction_text = ""
    if corrections:
        recent = corrections[-3:]
        correction_text = "\n从历史纠错中学到:\n" + "\n".join(
            f"- \"{c['query']}\" → {c['correct']} (非 {c['wrong']})" for c in recent
        )
    
    prompt = f"""你是一个意图路由专家。根据用户指令，从下面的技能列表中选出最合适的1-2个。

技能列表（共{len(skills)}个）:
{chr(10).join(skill_lines)}
{correction_text}
用户指令: 「{query}」

只输出JSON数组，不要其他文字:
[{{"skill": "技能slug", "confidence": 0-1之间的小数, "reason": "简短理由"}}]
如果没有匹配返回 []
    """
    
    # Try DeepSeek API
    try:
        import urllib.request
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1/chat/completions")
        
        if api_key:
            data = json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 500
            }).encode()
            req = urllib.request.Request(
                api_base,
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            content = resp["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            import re
            m = re.search(r'\[.*?\]', content, re.DOTALL)
            if m:
                results = json.loads(m.group())
                if isinstance(results, list) and len(results) > 0:
                    return results
    except Exception as e:
        pass
    
    return None

def route_with_keywords(query):
    """Fallback: use intent_router.py"""
    try:
        result = subprocess.run(
            [sys.executable, ROUTER_SCRIPT, "route", query],
            capture_output=True, text=True, timeout=10
        )
        # Parse the output
        import re
        # Extract skill slugs from output
        skills_found = re.findall(r'(\d+)%.*?\s+(\S+)\s+\((\S+)\)', result.stdout)
        results = []
        for score, name, slug in skills_found:
            results.append({"skill": slug, "confidence": int(score)/100, "reason": f"{name}"})
        return results if results else None
    except Exception:
        return None

def analyze_query(query):
    """Main: analyze user query, route to best skill, log everything"""
    results = route_with_llm(query)
    
    # Log
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "query": query,
        "result": results or [],
        "success": bool(results)
    }
    with open(HISTORY_FILE, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    # Update stats
    learning = load_learning()
    learning["stats"]["total_routes"] += 1
    save_learning(learning)
    
    return results

def record_correction(query, wrong, correct):
    """Learn from user correction"""
    learning = load_learning()
    learning["corrections"].append({
        "query": query, "wrong": wrong, "correct": correct,
        "timestamp": datetime.datetime.now().isoformat()
    })
    learning["stats"]["wrong"] += 1
    save_learning(learning)
    
    # Also update alias in router
    alias_path = os.path.join(WORKSPACE, "scripts", "intent_router.py")
    if os.path.exists(alias_path):
        with open(alias_path) as f:
            content = f.read()
        
        # Find the SKILL_ALIASES dict and add to the correct skill
        import re
        pattern = rf'"{re.escape(correct)}":\s*\[(.*?)\]'
        m = re.search(pattern, content, re.DOTALL)
        if m:
            existing = m.group(1)
            # Add query keywords as new aliases
            keywords = [w for w in re.findall(r'[\u4e00-\u9fff]{2,}', query) if len(w) >= 2]
            new_aliases = [f'"{k}"' for k in keywords if k not in existing]
            if new_aliases:
                new_line = f'"{correct}": [{existing.strip()}, {", ".join(new_aliases)}],'
                content = content.replace(f'"{correct}": [{existing}],', new_line)
                with open(alias_path, 'w') as f:
                    f.write(content)
    
    return True

def show_status():
    """Show agent status"""
    learning = load_learning()
    stats = learning["stats"]
    
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            for line in f:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    
    print(f"🤖 Intent Router Agent — 自进化意图路由")
    print(f"{'='*40}")
    print(f"📊 路由统计:")
    print(f"  总路由次数: {stats.get('total_routes', 0)}")
    print(f"  纠错学习: {len(learning.get('corrections', []))} 条")
    
    if history:
        print(f"\n🔄 最近路由:")
        for entry in history[-5:]:
            ts = entry.get("timestamp", "?")[:16]
            q = entry.get("query", "")[:25]
            r = entry.get("result", [])
            top = r[0]["skill"] if r else "❌"
            conf = r[0]["confidence"] if r else 0
            bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            print(f"  [{ts}] {bar} {q} → {top}")

def main():
    if len(sys.argv) < 2:
        print("用法: intent_router_agent.py [route <query>|correct <q> <wrong> <right>|status]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "route":
        query = " ".join(sys.argv[2:])
        if not query:
            print("❌ 请提供查询内容")
            sys.exit(1)
        results = analyze_query(query)
        if results:
            print(f"🔀 路由: {query}")
            for r in results[:3]:
                bar = "█" * int(r["confidence"] * 10) + "░" * (10 - int(r["confidence"] * 10))
                print(f"  {bar} {r['confidence']:.0%}  {r['skill']} — {r.get('reason', '')}")
        else:
            print(f"❌ 未找到匹配: {query}")
    
    elif cmd == "correct":
        if len(sys.argv) < 5:
            print("❌ 用法: correct <query> <wrong_skill> <correct_skill>")
            sys.exit(1)
        record_correction(sys.argv[2], sys.argv[3], sys.argv[4])
        print("✅ 已学习！下次遇到类似指令会路由到正确技能")
    
    elif cmd == "status":
        show_status()
    
    else:
        print(f"未知命令: {cmd}")

if __name__ == "__main__":
    main()
