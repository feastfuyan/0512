# 数据结构参考

## 地缘政治模块 JSON 数据结构

### 1. event_timelines_corrected.json（事件时间线）

数组格式，每个元素为一个事件对象：

```json
[
  {
    "topic_fingerprint": "us-china-tariff-2026",
    "title": "美中关税升级：新一轮贸易摩擦",
    "events": [
      {
        "date": "2026-04-10",
        "title": "...",
        "source": "Reuters",
        "tier": "Tier-1",
        "summary": "...",
        "confidence": 0.85,
        "source_tier": "Tier-1"
      }
    ],
    "first_seen": "2026-04-09",
    "last_seen": "2026-04-12",
    "source_count": 5,
    "cross_validation": true
  }
]
```

### 2. scored_events.json（CRI评分）

数组格式，每个元素为评分后的事件：

```json
[
  {
    "event_title": "美中关税升级",
    "cri_score": 6.8,
    "risk_level": "高",
    "action": "重点关注",
    "dimensions": {
      "D1_geopolitical_tension": 8.2,
      "D2_supply_shock": 7.1,
      "D3_price_impact": 6.5,
      "D4_policy_direction": 5.8,
      "D5_duration": 6.4
    },
    "affected_commodities": ["copper", "lithium", "rare_earth"],
    "affected_regions": ["China", "Australia", "SEA"]
  }
]
```

### 3. cri_summary.json（CRI评分摘要）

```json
{
  "period": "2026-04-06 至 2026-04-12",
  "total_events": 15,
  "avg_cri": 4.7,
  "risk_distribution": {
    "极高": 1,
    "高": 3,
    "中": 6,
    "低": 5
  },
  "top_risk_events": [...],
  "commodity_exposure": {
    "copper": 7.2,
    "iron_ore": 5.1,
    "lithium": 6.8
  }
}
```

### 4. all_quantitative_latest.json（量化数据汇总）

数组格式，包含多种数据源：

```json
[
  {
    "source_key": "GPR_Index",
    "date": "2026-04-12",
    "gpr_daily": 82.4,
    "gpr_ma30": 78.6
  },
  {
    "source_key": "Commodity_Prices",
    "commodity": "copper",
    "date": "2026-04-12",
    "price": 9240,
    "change": "+2.3%"
  },
  {
    "source_key": "CN_AU_Trade",
    "date": "2026-04-12",
    "import": "145.2",
    "export": "98.7",
    "balance": "46.5"
  }
]
```

## 技能文件说明

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 技能主文档，包含完整的开发规范和使用说明 |
| `assets/MiningClaw__GeopoliticsReport_Bilingual.html` | HTML模板，红蓝渐变主题，支持动态数据填充 |
| `scripts/load-data.cjs` | 数据加载模块，读取JSON并预处理 |
| `scripts/generate-pdf.cjs` | PDF生成主脚本，包含图表生成和Playwright调用 |
| `scripts/splitOverflow.cjs` | 溢出修复脚本（从macro-pdf-report复用） |
| `package.json` | NPM配置，定义脚本入口和依赖 |
| `references/` | 参考资料（宏观报告技能+地缘政治模块源码） |
| `output/` | PDF输出目录 |

## 快速开始

```bash
# 1. 安装依赖
npm install

# 2. 运行报告生成（使用默认数据路径）
npm run generate

# 3. 自定义数据路径
npm run generate:custom 数据/地缘政治
```

## 当前实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| SKILL.md | ✅ | 已完成 |
| HTML模板 | ✅ | 封面+要点页+封底，红蓝渐变主题 |
| 数据加载 | ✅ | 支持event_timelines_corrected.json等4种JSON |
| CRI雷达图 | ✅ | SVG五边形实现 |
| P×I矩阵 | ⚠️ | 占位实现，需完整数据后完善 |
| PDF输出 | ✅ | Playwright集成+溢出修复 |
| 溢出修复 | ✅ | 从macro-pdf-report复用 |

## 待完善功能

- [ ] P×I风险矩阵热力图完整实现
- [ ] 事件时间线SVG
- [ ] 商品暴露度柱状图
- [ ] GPR指数走势图
- [ ] 风险分布环形图
- [ ] 完整的8页内容填充（P3-P6动态内容）

## 注意事项

1. **数据路径**：默认相对路径为`数据/地缘政治/`，运行前确保地缘政治模块已输出数据
2. **Playwright依赖**：首次运行需`npm install playwright`安装浏览器驱动
3. **PDF质量**：报告使用`printBackground: true`确保红蓝渐变正常渲染
4. **禁止臆造**：所有内容必须来自原始JSON，不得编造数据
