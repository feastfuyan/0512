#!/usr/bin/env python3
"""
确定性门禁检查器（Harness 铁律：质量门禁不交给 Agent 判断）
"""

import json
import sys
from datetime import datetime, timezone


def check_gates(score_json: dict) -> dict:
    """执行所有门禁检查，返回门禁结果"""
    gates = []
    meta = score_json.get("meta", {})
    data_src = score_json.get("data_source_assessment", {})
    critical_issues = score_json.get("critical_issues", [])

    # 门禁 1：总分
    total_score = meta.get("total_score", 0)
    if total_score < 6.0:
        gates.append({
            "gate": "total_score",
            "status": "soft_fail",
            "value": total_score,
            "threshold": 6.0,
            "message": f"总分 {total_score}/10 低于 6.0，建议重新评估"
        })
    else:
        gates.append({
            "gate": "total_score",
            "status": "pass",
            "value": total_score
        })

    # 门禁 2：数据来源质量
    quality_score = data_src.get("quality_score", 0)
    if quality_score > 0 and quality_score < 4.0:
        gates.append({
            "gate": "data_quality",
            "status": "soft_fail",
            "value": quality_score,
            "threshold": 4.0,
            "message": f"数据来源质量分 {quality_score}/10 低于 4.0"
        })
    else:
        gates.append({
            "gate": "data_quality",
            "status": "pass" if quality_score > 0 else "not_applicable",
            "value": quality_score
        })

    # 门禁 3：严重问题数量
    if len(critical_issues) >= 5:
        gates.append({
            "gate": "too_many_issues",
            "status": "soft_fail",
            "value": len(critical_issues),
            "threshold": 5,
            "message": f"严重问题 {len(critical_issues)} 个，超过阈值 5"
        })
    else:
        gates.append({
            "gate": "too_many_issues",
            "status": "pass",
            "value": len(critical_issues)
        })

    # 综合评价
    soft_fails = [g for g in gates if g["status"] == "soft_fail"]
    if soft_fails:
        overall_status = "soft_fail"
        overall_message = "; ".join(g.get("message", g["gate"]) for g in soft_fails)
    else:
        overall_status = "pass"
        overall_message = "所有门禁通过"

    return {
        "status": overall_status,
        "message": overall_message,
        "gates": gates,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python gate_checker.py <score_json_path>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        score_json = json.load(f)

    result = check_gates(score_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["status"] == "soft_fail":
        sys.exit(0)  # soft fail 不阻塞流程，仅标记
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
