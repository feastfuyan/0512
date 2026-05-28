#!/usr/bin/env python3
"""
LynHarness Workflow Engine v1.1
读取 YAML workflow → 按依赖拓扑执行节点 → 支持并行 fanout + token 记账

Harness 原则：
- 节点类型: agent | script | human_in_loop
- Context Mode: fresh（默认，直接注入 artifact 内容）/ continue（暂未实现）
- 确定性门禁: script 节点，不交给 Agent 判断
- Token 记账: 每节点记录 input/output tokens
"""

import yaml
import json
import os
import sys
import time
import uuid
import copy
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Data Models ───────────────────────────────────────────────

STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_PAUSED = "paused"

MAX_PROMPT_CHARS = 30000  # 注入 artifact 内容的上限


@dataclass
class NodeResult:
    node_id: str
    node_type: str
    status: str  # success | failure | paused
    outputs: dict[str, Any] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None


# ── Core Engine ────────────────────────────────────────────────

class WorkflowEngine:
    """轻量 Harness 执行引擎"""

    def __init__(self, concurrency: int = 4):
        self.concurrency = concurrency
        self.runners: dict[str, "NodeRunner"] = {}
        self.token_log: list[dict] = []
        self._executor = None

    def register_runner(self, runner: "NodeRunner") -> None:
        self.runners[runner.node_type] = runner

    def load_workflow(self, path: str) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def execute(self, workflow: dict, inputs: dict) -> list[NodeResult]:
        """拓扑排序 + 并行执行（线程安全）"""
        nodes = workflow.get("nodes", [])
        artifacts_dir = workflow.get("artifacts_dir", "./output/").replace(
            "{{ run_id }}", inputs.get("run_id", str(int(time.time())))
        )
        os.makedirs(Path(artifacts_dir), exist_ok=True)

        completed: dict[str, NodeResult] = {}
        node_map: dict[str, dict] = {n["id"]: n for n in nodes}

        # 单线程池，整个工作流生命周期复用
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:

            while len(completed) < len(nodes):
                ready = [
                    node
                    for node in nodes
                    if node["id"] not in completed
                    and all(
                        d in completed and completed[d].status == STATUS_SUCCESS
                        for d in node.get("depends_on", [])
                    )
                ]

                if not ready:
                    # 检查是否死锁
                    remaining = [n for n in nodes if n["id"] not in completed]
                    has_paused_dep = any(
                        n["id"] not in completed
                        and any(
                            d in completed and completed[d].status == STATUS_PAUSED
                            for d in n.get("depends_on", [])
                        )
                        for n in remaining
                    )
                    if has_paused_dep:
                        print(f"\n⏸️  工作流暂停于 {len(completed)}/{len(nodes)} 节点（有 paused 节点）")
                    else:
                        failed = {nid: r for nid, r in completed.items() if r.status == STATUS_FAILURE}
                        raise RuntimeError(
                            f"Deadlock: {len(remaining)} 节点无法执行。"
                            f"已完成: {list(completed.keys())}, 失败: {list(failed.keys())}"
                        )
                    break

                # 并行执行 ready 节点（传递 completed 的浅拷贝避免竞态）
                ctx_map: dict[str, dict] = {}
                futures = {}
                for node in ready:
                    ctx = {
                        "run_id": inputs.get("run_id", ""),
                        "artifacts_dir": artifacts_dir,
                        "inputs": inputs,
                        "completed": copy.copy(completed),  # 线程安全的快照
                    }
                    ctx_map[node["id"]] = ctx
                    futures[executor.submit(self._run_node, node, ctx)] = node

                for future in as_completed(futures):
                    node = futures[future]
                    try:
                        result = future.result(timeout=node.get("timeout", 300))
                    except Exception as e:
                        result = NodeResult(
                            node_id=node["id"],
                            node_type=node.get("type", "agent"),
                            status=STATUS_FAILURE,
                            error=str(e),
                        )
                    completed[result.node_id] = result

                    # Token 记账
                    if result.token_usage:
                        self.token_log.append({
                            "node_id": result.node_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "model": node.get("model", "N/A"),
                            "input_tokens": result.token_usage.get("input_tokens", 0),
                            "output_tokens": result.token_usage.get("output_tokens", 0),
                            "total_tokens": result.token_usage.get("total_tokens", 0),
                        })

                    if result.status == STATUS_FAILURE:
                        print(f"\n❌ Node '{result.node_id}' failed: {result.error}")
                        # 取消剩余 future，但不立即返回 — 收集所有已完成的结果
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        return list(completed.values())

        return list(completed.values())

    def _run_node(self, node: dict, ctx: dict) -> NodeResult:
        """运行单个节点"""
        node_type = node.get("type", "agent")
        runner = self.runners.get(node_type)

        if runner is None:
            raise ValueError(f"No runner registered for node type: {node_type}")

        rendered_node = self._render_template(node, ctx)
        return runner.run(rendered_node, ctx)


# ── Template Engine ────────────────────────────────────────────

class TemplateEngine:
    """轻量模板引擎：支持 {{ a.b.c }} 路径导航 + 文件内容注入 {{ >filename }}"""

    @staticmethod
    def render(text: str, ctx: dict) -> str:
        import re

        def replacer(m):
            expr = m.group(1).strip()
            # 文件注入: {{ >filename }} → 读取文件内容
            if expr.startswith(">"):
                filename = expr[1:].strip()
                artifacts_dir = ctx.get("artifacts_dir", ".")
                path = os.path.join(artifacts_dir, filename)
                if os.path.exists(path):
                    with open(path, "r") as f:
                        content = f.read()
                    if len(content) > MAX_PROMPT_CHARS:
                        print(f"  ⚠️  {filename} 内容 {len(content)} 字符，截断到 {MAX_PROMPT_CHARS}")
                        content = content[:MAX_PROMPT_CHARS]
                    return content
                return f"[文件不存在: {filename}]"

            # 路径导航: {{ a.b.c }}
            parts = expr.split(".")
            value = ctx
            try:
                for p in parts:
                    if isinstance(value, dict):
                        value = value.get(p, f"{{{{ {expr} }}}}")
                    elif isinstance(value, NodeResult):
                        value = value.outputs.get(p, f"{{{{ {expr} }}}}")
                    elif hasattr(value, p):
                        value = getattr(value, p)
                    else:
                        return f"{{{{ {expr} }}}}"
                return str(value)
            except Exception:
                return f"{{{{ {expr} }}}}"

        return re.sub(r"\{\{\s*(.+?)\s*\}\}", replacer, text)

    @staticmethod
    def render_obj(obj: Any, ctx: dict) -> Any:
        if isinstance(obj, str):
            return TemplateEngine.render(obj, ctx)
        if isinstance(obj, dict):
            return {k: TemplateEngine.render_obj(v, ctx) for k, v in obj.items()}
        if isinstance(obj, list):
            return [TemplateEngine.render_obj(v, ctx) for v in obj]
        return obj


# ── Global instance ────────────────────────────────────────────
_engine = TemplateEngine()

# Backward compatibility
def _render_template(obj, ctx):
    return _engine.render_obj(obj, ctx)

render_template = _engine.render


# ── Node Runners ───────────────────────────────────────────────

class NodeRunner:
    node_type: str = "base"

    def run(self, node: dict, ctx: dict) -> NodeResult:
        raise NotImplementedError


class ScriptNodeRunner(NodeRunner):
    """确定性脚本节点 — Harness 铁律：质量门禁不用 Agent 判断"""

    node_type = "script"

    def run(self, node: dict, ctx: dict) -> NodeResult:
        start = time.time()
        runtime = node.get("runtime", "bash")
        command = node["command"]
        artifacts_dir = ctx["artifacts_dir"]

        env = os.environ.copy()
        env["ARTIFACTS_DIR"] = artifacts_dir
        env["RUN_ID"] = ctx.get("run_id", "")

        try:
            if runtime == "python":
                result = subprocess.run(
                    [sys.executable, "-c", command],
                    capture_output=True,
                    text=True,
                    timeout=node.get("timeout", 60),
                    cwd=os.getcwd(),
                    env=env,
                )
            else:
                result = subprocess.run(
                    ["bash", "-c", command],
                    capture_output=True,
                    text=True,
                    timeout=node.get("timeout", 60),
                    cwd=os.getcwd(),
                    env=env,
                )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            if stdout:
                print(f"  [{node['id']}] {stdout[:200]}")
            if stderr and result.returncode != 0:
                print(f"  [{node['id']}] ERR: {stderr[:200]}")

            return NodeResult(
                node_id=node["id"],
                node_type="script",
                status=STATUS_SUCCESS if result.returncode == 0 else STATUS_FAILURE,
                outputs={"stdout": stdout, "stderr": stderr, "exit_code": result.returncode},
                duration_ms=int((time.time() - start) * 1000),
                error=stderr if result.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            return NodeResult(
                node_id=node["id"], node_type="script", status=STATUS_FAILURE,
                error=f"Timeout after {node.get('timeout', 60)}s",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(
                node_id=node["id"], node_type="script", status=STATUS_FAILURE,
                error=str(e), duration_ms=int((time.time() - start) * 1000),
            )


class AgentNodeRunner(NodeRunner):
    """AI Agent 节点 — 调用 LLM 评分"""

    node_type = "agent"

    def run(self, node: dict, ctx: dict) -> NodeResult:
        start = time.time()
        artifacts_dir = ctx["artifacts_dir"]

        provider = node.get("provider", "deepseek")
        model_id = node["model"]
        context_mode = node.get("context_mode", "fresh")
        outputs_config = node.get("outputs", {})

        try:
            # 构建完整 prompt（注入 artifact 文件内容）
            full_prompt = self._build_prompt(node, ctx, artifacts_dir)

            # 调用模型
            response, token_usage = self._call_model(provider, model_id, full_prompt)

            # 保存输出 artifacts
            for key, filename in outputs_config.items():
                output_path = os.path.join(artifacts_dir, filename)
                # 尝试提取 JSON
                save_content = self._extract_json(response)
                with open(output_path, "w") as f:
                    f.write(save_content)
                print(f"  [{node['id']}] → {output_path} ({len(save_content)} chars)")

            duration = int((time.time() - start) * 1000)
            output_data = self._parse_json_response(response)

            return NodeResult(
                node_id=node["id"],
                node_type="agent",
                status=STATUS_SUCCESS,
                outputs=output_data,
                token_usage=token_usage,
                duration_ms=duration,
            )
        except Exception as e:
            return NodeResult(
                node_id=node["id"], node_type="agent", status=STATUS_FAILURE,
                error=str(e), duration_ms=int((time.time() - start) * 1000),
            )

    def _build_prompt(self, node: dict, ctx: dict, artifacts_dir: str) -> str:
        """构建完整 prompt — context_mode: fresh 时注入 artifact 文件内容"""
        prompt = node.get("prompt", "")

        # 注入 inputs 映射的文件内容（通过 {{ >filename }} 语法）
        inputs = node.get("inputs", {})
        for key, filename in inputs.items():
            path = os.path.join(artifacts_dir, str(filename))
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read()
                if len(content) > MAX_PROMPT_CHARS:
                    print(f"  ⚠️  [{node['id']}] {filename} {len(content)} chars, 截断")
                    content = content[:MAX_PROMPT_CHARS]
                # 用 {{ key }} 占位符替换为文件内容
                prompt = prompt.replace(f"{{{{ {key} }}}}", content)

        # 渲染剩余的 {{ }} 模板变量
        prompt = _engine.render(prompt, ctx)

        # context_mode: fresh 时，不注入之前 agent 的对话历史
        # （未来：context_mode: continue 时从 completed 中读取对话历史）
        return prompt

    def _call_model(self, provider: str, model_id: str, prompt: str) -> tuple[str, dict]:
        """调用 LLM API"""
        scripts_dir = os.path.join(os.path.dirname(__file__))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import score as score_mod

        content, token_usage = score_mod.call_model(provider, model_id, prompt)
        return content, token_usage

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 响应中提取纯 JSON 保存"""
        import re
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1)
        # 尝试找到第一个 { 到最后一个 }
        first = text.find('{')
        last = text.rfind('}')
        if first >= 0 and last > first:
            return text[first:last + 1]
        return text

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """尝试解析 JSON 响应"""
        json_str = AgentNodeRunner._extract_json(text)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {"raw_output": text}


class HumanInLoopRunner(NodeRunner):
    """人在回路节点"""

    node_type = "human_in_loop"

    def run(self, node: dict, ctx: dict) -> NodeResult:
        artifacts_dir = ctx["artifacts_dir"]
        prompt = node.get("prompt_to_user", "请审核结果并回复 'approve' 继续")
        gate_result_path = os.path.join(artifacts_dir, "gate_result.json")

        gate_status = "N/A"
        if os.path.exists(gate_result_path):
            with open(gate_result_path) as f:
                gate_result = json.load(f)
                gate_status = gate_result.get("status", "N/A")

        print(f"\n{'='*60}")
        print(f"👤 人工审核节点: {node['id']}")
        print(f"   Artifacts: {artifacts_dir}")
        print(f"   Gate: {gate_status}")
        print(f"   {prompt}")
        print(f"{'='*60}")

        auto_approve = os.environ.get("SCORECARD_AUTO_APPROVE", "").lower() == "true"
        if auto_approve:
            print("   [AUTO_APPROVE] 跳过人工审核")
            return NodeResult(
                node_id=node["id"], node_type="human_in_loop",
                status=STATUS_SUCCESS, outputs={"approved": True, "auto": True},
            )

        try:
            user_input = input("   → 输入 'approve' 继续，或按 Ctrl+C 取消: ").strip().lower()
            if user_input == "approve":
                return NodeResult(
                    node_id=node["id"], node_type="human_in_loop",
                    status=STATUS_SUCCESS, outputs={"approved": True},
                )
            else:
                return NodeResult(
                    node_id=node["id"], node_type="human_in_loop",
                    status=STATUS_PAUSED, outputs={"approved": False},
                )
        except KeyboardInterrupt:
            return NodeResult(
                node_id=node["id"], node_type="human_in_loop",
                status=STATUS_PAUSED, outputs={"approved": False, "cancelled": True},
            )


# ── CLI Entry Point ────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="LynHarness Workflow Engine")
    parser.add_argument("workflow", help="工作流 YAML 路径")
    parser.add_argument("--input", "-i", default="{}", help="输入参数 JSON")
    parser.add_argument("--concurrency", "-c", type=int, default=4, help="并行度")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    inputs = json.loads(args.input) if args.input else {}
    inputs.setdefault("run_id", str(uuid.uuid4())[:8])

    engine = WorkflowEngine(concurrency=args.concurrency)
    engine.register_runner(ScriptNodeRunner())
    engine.register_runner(AgentNodeRunner())
    engine.register_runner(HumanInLoopRunner())

    workflow = engine.load_workflow(args.workflow)

    print(f"\n🚀 LynHarness: {workflow['name']} v{workflow['version']}")
    print(f"   Run ID: {inputs['run_id']}")
    print(f"   Nodes: {len(workflow['nodes'])}")
    print()

    start = time.time()
    results = engine.execute(workflow, inputs)
    total_ms = int((time.time() - start) * 1000)

    success_count = sum(1 for r in results if r.status == STATUS_SUCCESS)
    failure_count = sum(1 for r in results if r.status == STATUS_FAILURE)
    total_input = sum(r.token_usage.get("input_tokens", 0) for r in results)
    total_output = sum(r.token_usage.get("output_tokens", 0) for r in results)

    print(f"\n{'='*60}")
    print(f"✅ Workflow 完成")
    print(f"   耗时: {total_ms}ms")
    print(f"   节点: {success_count} 成功, {failure_count} 失败")
    print(f"   总计 Token: {total_input} in / {total_output} out")

    # 保存 token 日志
    if engine.token_log:
        artifacts_dir = workflow.get("artifacts_dir", "./output/").replace(
            "{{ run_id }}", inputs["run_id"]
        )
        token_log_path = os.path.join(artifacts_dir, "token_usage.json")
        with open(token_log_path, "w") as f:
            json.dump(engine.token_log, f, ensure_ascii=False, indent=2)
        print(f"   Token 日志: {token_log_path}")

    # 保存运行报告
    run_report = {
        "workflow": workflow["name"],
        "version": workflow["version"],
        "run_id": inputs["run_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": total_ms,
        "nodes_total": len(workflow["nodes"]),
        "nodes_success": success_count,
        "nodes_failure": failure_count,
        "token_usage": {"input_tokens": total_input, "output_tokens": total_output},
        "node_results": [
            {"node_id": r.node_id, "status": r.status, "duration_ms": r.duration_ms, "error": r.error}
            for r in results
        ],
    }

    artifacts_dir = workflow.get("artifacts_dir", "./output/").replace(
        "{{ run_id }}", inputs["run_id"]
    )
    report_path = os.path.join(artifacts_dir, "run_report.json")
    with open(report_path, "w") as f:
        json.dump(run_report, f, ensure_ascii=False, indent=2)

    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
