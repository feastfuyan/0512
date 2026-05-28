#!/usr/bin/env python3
"""
test_scoring.py — 评分逻辑单元测试

覆盖：配置加载、权重计算、等级映射、分数解析、数据源评估、边界情况
"""

import sys
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from score import (
    load_config,
    get_available_templates,
    calculate_weighted_score,
    get_grade,
    parse_model_output,
    assess_data_sources,
)


def test_load_configs():
    """测试所有配置文件都能正常加载"""
    templates = get_available_templates()
    assert len(templates) >= 4, f"期望至少4个模板，实际 {len(templates)}"

    for name in templates:
        config = load_config(name)
        assert "dimensions" in config, f"{name}: 缺少 dimensions"
        assert "grade_scale" in config, f"{name}: 缺少 grade_scale"
        assert len(config["dimensions"]) >= 8, f"{name}: 维度数 {len(config['dimensions'])} < 8"

        # 验证每个维度有必要字段
        for dim in config["dimensions"]:
            assert "id" in dim, f"{name}: 维度缺少 id"
            assert "name" in dim, f"{name}: 维度缺少 name"
            assert "weight" in dim, f"{name}: {dim['id']} 缺少 weight"
            assert dim["weight"] > 0, f"{name}: {dim['id']} 权重 <= 0"

    print(f"✅ 配置加载测试通过 ({len(templates)} 个模板)")


def test_weighted_score():
    """测试加权分数计算"""
    config = load_config("default")
    dims = config["dimensions"]

    # 全满分
    scores = {d["id"]: 10.0 for d in dims}
    avg = calculate_weighted_score(dims, scores)
    assert avg == 10.0, f"全满分应得 10.0，实际 {avg}"

    # 全零分
    scores = {d["id"]: 0.0 for d in dims}
    avg = calculate_weighted_score(dims, scores)
    assert avg == 0.0, f"全零分应得 0.0，实际 {avg}"

    # 部分分数
    scores = {dims[0]["id"]: 8.0, dims[1]["id"]: 6.0}
    avg = calculate_weighted_score(dims, scores)
    assert 6.0 <= avg <= 8.0, f"部分分数应在 6-8 之间，实际 {avg}"

    # 空输入
    avg = calculate_weighted_score(dims, {})
    assert avg == 0.0, f"空输入应得 0.0，实际 {avg}"

    # N/A 字符串
    scores = {dims[0]["id"]: "N/A", dims[1]["id"]: 8.0}
    avg = calculate_weighted_score(dims, scores)
    assert avg > 0, f"N/A 应跳过，其余正常计算"

    print("✅ 加权分数计算测试通过")


def test_grade_mapping():
    """测试等级映射"""
    scale = [
        {"min_score": 9.6, "grade": "A+", "label": "顶级"},
        {"min_score": 9.0, "grade": "A", "label": "优秀"},
        {"min_score": 8.0, "grade": "B+", "label": "良好"},
        {"min_score": 7.0, "grade": "B", "label": "及格"},
        {"min_score": 6.0, "grade": "C", "label": "需修改"},
        {"min_score": 0, "grade": "F", "label": "不合格"},
    ]

    assert get_grade(9.8, scale) == ("A+", "顶级")
    assert get_grade(9.2, scale) == ("A", "优秀")
    assert get_grade(8.5, scale) == ("B+", "良好")
    assert get_grade(7.3, scale) == ("B", "及格")
    assert get_grade(6.1, scale) == ("C", "需修改")
    assert get_grade(5.9, scale) == ("F", "不合格")
    assert get_grade(0.0, scale) == ("F", "不合格")

    print("✅ 等级映射测试通过")


def test_parse_json_output():
    """测试 JSON 输出解析"""
    config = load_config("default")

    # 标准 JSON 输出
    raw = '''```json
{
    "dimensions": [
        {"id": "thesis_clarity", "name": "论点清晰度", "score": 8.5, "evaluation": "好", "improvement": "无", "evidence": "摘要"},
        {"id": "data_anchoring", "name": "数据支撑度", "score": 7.0, "evaluation": "尚可", "improvement": "补充来源", "evidence": "数据"}
    ],
    "highlights": ["亮点1"],
    "critical_issues": ["问题1"],
    "optimization_suggestions": [{"priority": "high", "area": "数据", "current_state": "缺", "suggestion": "加", "impact": "好"}]
}
```'''
    result = parse_model_output(raw, config)
    assert result["total_score"] > 0, "应有有效总分"
    assert len(result["highlights"]) == 1
    assert result["grade"] in ("A+", "A", "B+", "B", "C", "F")

    # N/A 分数
    raw_na = '{"dimensions":[{"id":"thesis_clarity","name":"论点","score":"N/A","evaluation":"","improvement":"","evidence":""}]}'
    result = parse_model_output(raw_na, config)
    # N/A 维度不计入总分

    print("✅ JSON 解析测试通过")


def test_data_source_assessment():
    """测试数据来源评估"""
    # 有权威来源
    text1 = "根据世界银行2025年报告，全球GDP增长达3.2%。据IEA数据显示，原油需求增长1.5%。"
    ds1 = assess_data_sources(text1)
    assert ds1["sources_found"] >= 1, f"应发现数据引用，实际 {ds1}"
    assert ds1["classified"]["authoritative"] >= 1, "应识别权威来源"

    # 无来源
    text2 = "这是一段没有任何数据引用的纯文字描述。"
    ds2 = assess_data_sources(text2)
    assert ds2["sources_found"] == 0 or ds2["quality_score"] < 5

    # 中英混合
    text3 = "According to Bloomberg, 铜价同比增长15%。Source: USGS Mineral Commodity Summaries 2025"
    ds3 = assess_data_sources(text3)
    assert ds3["sources_found"] >= 1

    print("✅ 数据来源评估测试通过")


def test_boundary_cases():
    """测试边界情况"""
    config = load_config("default")

    # 空模型输出
    result = parse_model_output("", config)
    assert result["total_score"] == 0.0

    # 只有部分文本的输出
    result = parse_model_output("评分结果：论点清晰度 8 分，数据支撑度 6 分", config)
    # 应该能从回退正则提取一些分数

    # 超长文本
    long_text = "根据世界银行报告" * 1000
    ds = assess_data_sources(long_text)
    assert ds["sources_found"] > 0

    print("✅ 边界情况测试通过")


if __name__ == "__main__":
    print("🧪 运行评分逻辑单元测试...\n")
    test_load_configs()
    test_weighted_score()
    test_grade_mapping()
    test_parse_json_output()
    test_data_source_assessment()
    test_boundary_cases()
    print("\n✅ 全部测试通过！")
