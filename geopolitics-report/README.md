# 地缘政治风险监控报告生成技能

## 📋 快速开始

### 一键生成
```bash
# 进入技能目录
cd ~/Desktop/地缘政治报告技能

# 生成PDF报告（使用默认数据）
node scripts/generate-pdf.cjs

# PDF会自动打开并播放提示音
```

### 自定义数据路径
```bash
# 如果数据在其他位置
node scripts/generate-pdf.cjs /path/to/your/data
```

---

## 📁 技能概述

生成专业的 A4 PDF 地缘政治风险监控报告，包含：
- 封面（深炭色 + 琥珀/teal光效）
- 报告要点（AI GENERATED徽章）
- 全球事件概览（统计卡片 + Tier分级表）
- 热点事件追踪（Top 5 事件卡片）
- CRI五维评分分析（雷达图）
- 大宗商品与矿业影响
- P×I风险矩阵与策略建议
- 封底

---

## 🎨 设计规范

### 配色系统
| 用途 | 颜色 |
|------|------|
| 封面光效 | 琥珀色 (#fcd34d) |
| 页头logo | teal色 (#14b8a6) |
| CRI评分条 | teal色 (#14b8a6) + 透明度 |
| 风险等级-极高 | 金橙色 (#f59e0b) |
| 风险等级-高 | 橙黄色 (#eab308) |
| 风险等级-中 | 蓝色 (#3b82f6) |
| 风险等级-低 | 绿色 (#10b981) |
| 封面背景 | 深炭色 (#0f1115) |

### 字体
- 中文：Noto Sans SC
- 英文/数字：Inter / Space Grotesk
- 标题：17px
- 正文：11.5px

### 图表
- SVG手写计算坐标
- 设备缩放2×（高清晰度）
- 6个SVG图表（雷达图、散点图、折线图、条形图、环形图、热力图）

---

## 📊 数据来源

数据文件位于：`数据/地缘政治/`（符号链接到数据目录）

- `event_timelines_corrected.json` - 事件时间线（84条）
- `scored_events.json` - CRI评分事件（80条）
- `cri_summary.json` - CRI评分摘要
- `all_quantitative_latest.json` - 量化数据（GPR指数、商品价格、贸易数据）

---

## 📝 文件结构

```
地缘政治报告技能/
├── SKILL.md                          ← 技能文档
├── README.md                         ← 快速开始指南
├── package.json                      ← 依赖配置
├── assets/
│   └── MiningClaw__GeopoliticsReport_Bilingual.html  ← HTML模板（39K）
├── scripts/
│   ├── generate-pdf.cjs               ← PDF生成主模块
│   ├── load-data.cjs                  ← 数据加载
│   └── splitOverflow.cjs               ← 分页控件
├── output/                            ← 生成的PDF
├── 数据/地缘政治/                    ← 数据目录（符号链接）
└── 文件清单.json                     ← 文件清单
```

---

## 🔄 更新日志

### v1.0.0 (2026-04-13)
- ✅ 初始版本完成
- ✅ 8页完整报告
- ✅ 6个SVG图表
- ✅ teal主题色系
- ✅ 封面琥珀色光效
- ✅ 评分条透明度区分
- ✅ 分页溢出自动处理

---

## ⚠️ 注意事项

1. **数据依赖**：生成前请确保数据目录存在
2. **Playwright**：首次运行会自动安装浏览器
3. **模板自动更新**：每次生成后模板会自动更新为最新版本
4. **分页自动处理**：内容过长会自动拆分到新页

---

## 📞 技术支持

- HTML/CSS：完全手写，无外部框架
- 图表：原生SVG，无图表库
- PDF引擎：Playwright（Chromium）
- 分页算法：自定义溢出检测

---

**MiningClaw AI Intelligence Systems** © 2026
