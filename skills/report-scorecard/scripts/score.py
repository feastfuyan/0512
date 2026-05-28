#!/usr/bin/env python3
import os
"""
score.py — 核心评分引擎 v2.0

职责：
1. 加载 YAML 配置（维度、权重、等级）
2. 读取报告内容（通过 report_parser）
3. 构建评分 prompt
4. 调用模型评分（支持多模型）
5. 解析结果为结构化 JSON
6. 计算加权总分和等级
7. 评估数据来源质量
8. 生成优化建议
9. 保存结果

依赖：Python 3.10+，PyYAML，标准库
"""

import json
import os
import re
import ssl
import time
import urllib.request
import hashlib
from datetime import datetime
from pathlib import Path

# ============================================================
# 常量
# ============================================================

MAX_PROMPT_CHARS = 30000
MAX_MODEL_TOKENS = 8192
MODEL_TIMEOUT = 120
MAX_RETRIES = 3

# ============================================================
# 配置加载
# ============================================================

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"
OUTPUT_DIR = Path(os.environ.get(
    "SCORECARD_OUTPUT_DIR",
    str(Path.home() / "Documents" / "MiningClawd" / "scorecards")
))


def load_config(template: str = "default") -> dict:
    """加载评分配置 YAML"""
    import yaml
    config_path = CONFIG_DIR / f"{template}.yaml"
    if not config_path.exists():
        available = [p.stem for p in CONFIG_DIR.glob("*.yaml")]
        raise FileNotFoundError(
            f"模板 '{template}' 不存在。可用模板: {available}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def get_available_templates() -> list[str]:
    """获取所有可用模板名"""
    return [p.stem for p in CONFIG_DIR.glob("*.yaml")]


# ============================================================
# 评分计算
# ============================================================

def calculate_weighted_score(dimensions: list[dict], scores: dict[str, float]) -> float:
    """
    计算加权总分。

    Args:
        dimensions: 配置中的维度列表
        scores: {dimension_id: score}

    Returns:
        float: 加权平均分
    """
    total_weighted = 0.0
    total_weight = 0.0

    for dim in dimensions:
        dim_id = dim["id"]
        weight = dim.get("weight", 1.0)
        score = scores.get(dim_id)

        # 跳过非数值分数（如 "N/A"）
        if score is not None:
            try:
                score = float(score)
            except (ValueError, TypeError):
                continue
            total_weighted += score * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    weighted_avg = round(total_weighted / total_weight, 1)
    return weighted_avg


def get_grade(score: float, grade_scale: list[dict]) -> tuple[str, str]:
    """根据分数获取等级"""
    for entry in sorted(grade_scale, key=lambda x: x["min_score"], reverse=True):
        if score >= entry["min_score"]:
            return entry["grade"], entry["label"]
    return "F", "不合格"


# ============================================================
# 数据来源评估
# ============================================================

DATA_SOURCE_PATTERNS = [
    # 中文数据引用模式
    (r"根据\s*([^\s,，。；;]{2,30})", "zh_source"),
    (r"数据显示[：:]?\s*([^\s,，。；;]{2,30})", "zh_data"),
    (r"(\d{4})[年](\d{1,2})[月]?[\s]*(?:报告|年报|季报|数据)", "zh_report"),
    # 英文数据引用模式
    (r"(?:according to|based on|cited in|data from|source:?)\s*([^\.,;]{2,50})", "en_source"),
    (r"\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*\d{4}[a-z]?)\)", "academic_cite"),
    # URL 模式
    (r"https?://[^\s\)\]>\"']+", "url"),
    # 数值引用
    (r"(?:达|约为|超过|接近|同比增长)\s*[\d,.]+\s*[%万亿元美金]", "zh_number"),
    (r"(?:increased|decreased|reached|approximately)\s*[\d,.]+\s*%?", "en_number"),
]

AUTHORITATIVE_SOURCES = [
    "ASX", "Australian Securities Exchange", "ASIC", "AASB", "JORC", "NI 43-101",
    "World Bank", "IMF", "OECD", "IEA", "USGS", "BGS", "Australian Bureau of Statistics",
    "Reserve Bank of Australia", "Reserve Bank", "RBA", "CIA World Factbook",
    "BMI Research", "Fitch", "S&P", "Moody's", "KPMG", "PwC", "Deloitte", "EY",
    "世界银行", "国际货币基金组织", "国际能源署", "经合组织",
    "国家统计局", "矿业部", "Department of",
    "联合国", "欧盟", "WHO", "世界卫生组织",
]

RELIABLE_SOURCES = [
    "Reuters", "Bloomberg", "Financial Times", "The Australian", "Mining Weekly",
    "Mining.com", "SNL Metals", "Wood Mackenzie", "CRU",
]


def assess_data_sources(text: str) -> dict:
    """评估报告中的数据来源质量"""
    sources_found = []

    for pattern, source_type in DATA_SOURCE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            source_text = match if isinstance(match, str) else " ".join(match)
            quality = _classify_source(source_text)
            sources_found.append({
                "text": source_text[:100],
                "type": source_type,
                "quality": quality,
            })

    # 统计
    total = len(sources_found)
    by_quality = {"authoritative": 0, "reliable": 0, "questionable": 0, "unverifiable": 0}
    for s in sources_found:
        q = s["quality"]
        if q in by_quality:
            by_quality[q] += 1
        else:
            by_quality["questionable"] += 1

    # 计算数据质量分（0-10）
    if total == 0:
        quality_score = 0.0
    else:
        auth_ratio = by_quality["authoritative"] / total
        rel_ratio = by_quality["reliable"] / total
        qual_score = (auth_ratio * 10 + rel_ratio * 7 +
                      (1 - auth_ratio - rel_ratio) * 3)
        quality_score = round(min(qual_score, 10.0), 1)

    return {
        "sources_found": total,
        "classified": by_quality,
        "quality_score": quality_score,
        "top_sources": sources_found[:10],
    }


def _classify_source(source_text: str) -> str:
    """分类数据来源质量"""
    for auth in AUTHORITATIVE_SOURCES:
        if auth.lower() in source_text.lower():
            return "authoritative"
    for rel in RELIABLE_SOURCES:
        if rel.lower() in source_text.lower():
            return "reliable"
    if any(kw in source_text for kw in ["未标注", "来源不详", "据说", "传闻", "网络", "网友"]):
        return "unverifiable"
    return "questionable"


# ============================================================
# Prompt 构建
# ============================================================

def _safe_truncate(text: str, max_chars: int = MAX_PROMPT_CHARS) -> str:
    """安全截断文本（Python3 str 切片已保证字符完整性）"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def build_scoring_prompt(config: dict, report_text: str) -> str:
    """构建评分 prompt"""
    dim_descriptions = []
    for dim in config["dimensions"]:
        weight_str = f"（权重×{dim['weight']}）" if dim.get("weight", 1.0) != 1.0 else ""
        eq = dim.get("example_question", "")
        name_en = f" ({dim['name_en']})" if dim.get('name_en') else ""
        dim_descriptions.append(
            f"- **{dim['name']}{name_en}** {weight_str}\n"
            f"  说明: {dim['description']}\n"
            f"  检查: {eq}"
        )

    dims_text = "\n".join(dim_descriptions)

    prompt = f"""你是一名专业的报告质量评审专家。请对以下报告进行严格评分。

## 评分配置
模板: {config.get('name', '默认')}
维度数: {len(config['dimensions'])}

## 评分维度
{dims_text}

## 评分规则
- 每个维度 0-10 分，精确到 0.1
- 按权重计算加权总分
- 评分必须基于报告实际内容，不得凭空臆断
- 引用报告原文时标注位置
- 内容不足以评估的维度标为 N/A

## 输出要求
请严格按照以下 JSON 格式输出（不要输出其他内容）：

```json
{{
  "dimensions": [
    {{
      "id": "维度id",
      "name": "维度名",
      "score": 8.5,
      "evaluation": "一句话评价（好的方面）",
      "improvement": "一句话改进建议",
      "evidence": "引用报告原文作为评分依据"
    }}
  ],
  "highlights": ["亮点1", "亮点2", "亮点3"],
  "critical_issues": ["问题1", "问题2"],
  "optimization_suggestions": [
    {{
      "priority": "critical|high|medium",
      "area": "改进领域",
      "current_state": "当前状态",
      "suggestion": "具体改进方案",
      "impact": "预期影响"
    }}
  ]
}}
```

## 报告内容
{_safe_truncate(report_text)}
"""
    return prompt


# ============================================================
# 模型调用（支持多 provider）
# ============================================================

def _call_openai_api(base_url: str, api_key: str, model_id: str, prompt: str,
                    timeout: int = MODEL_TIMEOUT) -> tuple[str, dict]:
    """通用 OpenAI 兼容 API 调用（含重试、SSL 控制和 Token 记账）"""
    ctx = None
    if os.environ.get("SCORECARD_SKIP_SSL", "").lower() == "true":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_MODEL_TOKENS,
    }).encode("utf-8")

    req = urllib.request.Request(
        base_url, data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    )

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                token_info = {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
                return content, token_info
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                raise


DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API147_BASE_URL = os.environ.get("API147_BASE_URL", "https://api.147ai.cn/v1")


def call_deepseek(api_key: str, model_id: str, prompt: str, timeout: int = MODEL_TIMEOUT) -> tuple[str, dict]:
    """调用 DeepSeek API，返回 (content, token_usage)"""
    return _call_openai_api(f"{DEEPSEEK_BASE_URL}/chat/completions", api_key, model_id, prompt, timeout)


def call_147ai(api_key: str, model_id: str, prompt: str, timeout: int = MODEL_TIMEOUT) -> tuple[str, dict]:
    """调用 147ai 中转 API，返回 (content, token_usage)"""
    return _call_openai_api(f"{API147_BASE_URL}/chat/completions", api_key, model_id, prompt, timeout)


from functools import lru_cache

@lru_cache(maxsize=1)
def load_providers() -> dict[str, str]:
    """从 openclaw.json 加载 API key 配置（缓存1份，避免重复IO）"""
    openclaw_config = Path.home() / ".openclaw" / "openclaw.json"
    if not openclaw_config.exists():
        raise FileNotFoundError(f"未找到 openclaw.json: {openclaw_config}")
    with open(openclaw_config, "r") as f:
        cfg = json.load(f)
    providers = {}
    for pid, pdata in cfg.get("models", {}).get("providers", {}).items():
        providers[pid] = pdata.get("apiKey", "")
    return providers


def call_model(provider_id: str, model_id: str, prompt: str) -> tuple[str, dict]:
    """统一模型调用入口，返回 (content, token_usage)"""
    providers = load_providers()
    api_key = providers.get(provider_id, "")
    if not api_key:
        raise ValueError(f"未找到 provider '{provider_id}' 的 API key")

    if provider_id == "deepseek":
        return call_deepseek(api_key, model_id, prompt)
    elif provider_id == "api147":
        return call_147ai(api_key, model_id, prompt)
    else:
        raise ValueError(f"不支持的 provider: {provider_id}")


# ============================================================
# 结果解析
# ============================================================

def parse_model_output(raw_output: str, config: dict) -> dict:
    """解析模型输出为结构化结果"""
    # 尝试提取 JSON
    json_match = re.search(r'```json\s*(.*?)\s*```', raw_output, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 尝试直接解析整个输出
        json_str = raw_output

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        # 回退：用正则提取分数
        parsed = {"dimensions": [], "highlights": [], "critical_issues": [], "optimization_suggestions": []}
        for dim in config["dimensions"]:
            pattern = rf'{dim["id"]}["\s:]+(\d+\.?\d*)'
            match = re.search(pattern, raw_output)
            score = float(match.group(1)) if match else None
            parsed["dimensions"].append({
                "id": dim["id"],
                "name": dim["name"],
                "score": score,
                "evaluation": "",
                "improvement": "",
                "evidence": ""
            })

    # 计算加权总分
    dim_scores = {}
    for d in parsed.get("dimensions", []):
        if d.get("score") is not None:
            dim_scores[d["id"]] = d["score"]

    weighted_avg = calculate_weighted_score(config["dimensions"], dim_scores)
    grade, grade_label = get_grade(weighted_avg, config.get("grade_scale", []))

    return {
        "dimensions": parsed.get("dimensions", []),
        "highlights": parsed.get("highlights", []),
        "critical_issues": parsed.get("critical_issues", []),
        "optimization_suggestions": parsed.get("optimization_suggestions", []),
        "total_score": weighted_avg,
        "grade": grade,
        "grade_label": grade_label,
    }


# ============================================================
# 缓存机制
# ============================================================

def _cache_key(file_path: str, template: str) -> str:
    """生成缓存 key（含文件路径+修改时间+模板）"""
    mtime = str(os.path.getmtime(file_path))
    raw = f"{file_path}:{mtime}:{template}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _check_cache(key: str) -> dict | None:
    """检查缓存"""
    cache_path = OUTPUT_DIR / f".cache_{key}.json"
    if cache_path.exists():
        with open(cache_path, "r") as f:
            return json.load(f)
    return None


def _save_cache(key: str, data: dict):
    """保存缓存"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = OUTPUT_DIR / f".cache_{key}.json"
    with open(cache_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 主入口
# ============================================================

def score_report(
    file_path: str,
    template: str = "default",
    provider: str = "deepseek",
    model_id: str = "deepseek-v4-pro",
    use_cache: bool = True,
) -> dict:
    """
    评分主入口。

    Args:
        file_path: 报告文件路径
        template: 评分模板名（default/mining/legal/tech-eval）
        provider: 模型提供商（deepseek/api147）
        model_id: 模型ID
        use_cache: 是否使用缓存

    Returns:
        完整评分结果 dict
    """
    # 1. 检查缓存
    cache_k = _cache_key(file_path, template)
    if use_cache:
        cached = _check_cache(cache_k)
        if cached:
            cached["from_cache"] = True
            return cached

    # 2. 加载配置
    config = load_config(template)

    # 3. 解析报告
    from report_parser import parse_report
    report = parse_report(file_path)
    if report["error"]:
        return {"error": f"报告解析失败: {report['error']}"}

    text = report["text"]
    if len(text) < 100:
        return {"error": "报告内容过少（<100字符），无法评分"}

    # 4. 评估数据来源
    data_assessment = assess_data_sources(text)

    # 5. 构建并调用模型
    prompt = build_scoring_prompt(config, text)
    raw_output, token_usage = call_model(provider, model_id, prompt)

    # 6. 解析结果
    scored = parse_model_output(raw_output, config)

    # 7. 组装最终结果
    result = {
        "meta": {
            "report_name": Path(file_path).stem,
            "report_format": report["format"],
            "report_chars": report["char_count"],
            "score_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "template": template,
            "model": f"{provider}/{model_id}",
            "total_score": scored["total_score"],
            "grade": scored["grade"],
            "grade_label": scored["grade_label"],
        },
        "dimensions": scored["dimensions"],
        "data_source_assessment": data_assessment,
        "optimization_suggestions": scored["optimization_suggestions"],
        "highlights": scored["highlights"],
        "token_usage": token_usage,
        "critical_issues": scored["critical_issues"],
        "from_cache": False,
    }

    # 8. 保存
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"{Path(file_path).stem}_{template}_{timestamp}.json"
    with open(output_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    result["output_path"] = str(output_path)

    # 9. 缓存
    _save_cache(cache_k, result)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="报告评分引擎")
    parser.add_argument("file", help="报告文件路径")
    parser.add_argument("--template", default="default", help="评分模板")
    parser.add_argument("--provider", default="deepseek", help="模型提供商")
    parser.add_argument("--model", default="deepseek-v4-pro", help="模型ID")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    args = parser.parse_args()

    print(f"🔍 评分报告: {args.file}")
    print(f"   模板: {args.template}")
    print(f"   模型: {args.provider}/{args.model}")

    result = score_report(
        args.file,
        template=args.template,
        provider=args.provider,
        model_id=args.model,
        use_cache=not args.no_cache,
    )

    if "error" in result:
        print(f"❌ {result['error']}")
    else:
        m = result["meta"]
        print(f"\n✅ 评分完成")
        print(f"   总分: {m['total_score']}/10 — {m['grade']} ({m['grade_label']})")
        print(f"   数据来源: {result['data_source_assessment']['sources_found']} 处引用")
        print(f"   输出: {result.get('output_path', '')}")
