/**
 * cri-scorer.mjs — CRI 五维评分引擎
 *
 * 从 v1.2 地缘政治评分.py (GeopoliticalScorer) 移植
 * 基于事件类型、涉及矿种、描述内容、来源质量对每条事件进行 D1-D5 五维评分
 * 输出 CRI 综合指数 + 风险等级 + 行动建议 + 置信度
 *
 * CRI = 0.25×D1 + 0.25×D2 + 0.20×D3 + 0.15×(|D4|×2) + 0.15×D5
 * D4 是双极维度（-5 到 +5），在 CRI 计算中取 |D4|×2 归一化到 0-10
 */

// ─────────────────────────────────────────────────
// 权重配置 (V2 DevSpec MC-FW-2026-001)
// ─────────────────────────────────────────────────
export const WEIGHTS = {
  d1: 0.25,
  d2: 0.25,
  d3: 0.20,
  d4: 0.15,
  d5: 0.15,
};

// ─────────────────────────────────────────────────
// 事件类型映射：DB 英文 → v1.2 中文体系
// ─────────────────────────────────────────────────
const TYPE_MAP = {
  security: 'conflict',       // 默认 security → conflict，关键词可升级到 war
  sanctions: 'sanction',
  trade: 'tariff',            // 默认 trade → tariff，关键词可改为 trade_agreement
  critical_minerals: 'export_control',
};

// ─────────────────────────────────────────────────
// 关键词库
// ─────────────────────────────────────────────────
const WAR_KEYWORDS = ['war', 'invasion', 'missile', 'airstrike', 'bombing', 'offensive', 'escalat'];
const CONFLICT_KEYWORDS = ['conflict', 'tension', 'military', 'clash', 'deploy', 'troops', 'naval', 'air strike'];
const SANCTION_KEYWORDS = ['sanction', 'embargo', 'blockade', 'freeze', 'ban', 'restrict'];
const TARIFF_KEYWORDS = ['tariff', 'duty', 'trade war', 'dumping', 'countervail'];
const AGREEMENT_KEYWORDS = ['agreement', 'deal', 'pact', 'treaty', 'partnership', 'cooperat'];
const HIGH_IMPACT_MINERALS = ['Li', 'lithium', 'W', 'tungsten', 'Cu', 'copper', 'REE', 'rare earth', 'Oil', 'oil', 'Gas', 'gas', 'uranium', 'U', 'cobalt', 'Co'];
const PRICE_SIGNALS = ['price surge', 'price spike', 'supply cut', 'disruption', 'shortage', 'surge', 'plummet', 'crash', 'rally', 'soar'];
const SOURCE_QUALITY_HIGH = ['aspi', 'csis', 'reuters', 'bloomsberg', 'ft.com', 'economist', 'bbc', 'scmp'];

// ─────────────────────────────────────────────────
// D1 地缘紧张度 (0-10)
// ─────────────────────────────────────────────────
export function scoreD1(event) {
  let score = 2.0; // 降低基础分，增加区分度
  const text = ((event.title || '') + ' ' + (event.description || '')).toLowerCase();
  const mappedType = mapEventType(event);

  // 事件类型加分 — 降低幅度让分数有分散
  const tensionMap = {
    conflict: 2.5, war: 4.0, sanction: 2.0, export_control: 1.5,
    tariff: 1.0, shipping: 2.0, mine_closure: 1.0,
    trade_agreement: -1.0, investment: -0.5, other: 0,
  };
  score += tensionMap[mappedType] || 0;

  // 关键词加分 — 只有 war 级别关键词大幅加分
  if (WAR_KEYWORDS.some(kw => text.includes(kw))) score += 1.5;
  if (CONFLICT_KEYWORDS.some(kw => text.includes(kw))) score += 0.5;
  if (SANCTION_KEYWORDS.some(kw => text.includes(kw))) score += 0.3;

  // 描述质量加分 — 内容越丰富，评分越高（区分简短通知和深度分析）
  const descLen = (event.description || '').length;
  score += Math.min(descLen / 400, 1.5); // 0-1.5 based on description length

  // 来源质量
  const url = (event.source_url || '').toLowerCase();
  if (SOURCE_QUALITY_HIGH.some(s => url.includes(s))) score += 0.5;

  return clamp(score, 0, 10);
}

// ─────────────────────────────────────────────────
// D2 供应冲击 (0-10)
// ─────────────────────────────────────────────────
export function scoreD2(event) {
  let score = 2.0;
  const text = ((event.title || '') + ' ' + (event.description || '')).toLowerCase();
  const mappedType = mapEventType(event);

  // 涉及商品加分
  const commodities = event.commodities || [];
  for (const c of commodities) {
    if (HIGH_IMPACT_MINERALS.some(m => c.toLowerCase().includes(m.toLowerCase()))) {
      score += 2.0;
    } else {
      score += 0.5;
    }
  }

  // 文本中提到关键矿种
  const textMineralCount = HIGH_IMPACT_MINERALS.filter(m => text.includes(m.toLowerCase())).length;
  score += Math.min(textMineralCount * 0.8, 2.0);

  // 事件类型
  const supplyMap = {
    conflict: 2.0, war: 3.0, sanction: 1.5, export_control: 2.5,
    shipping: 2.0, mine_closure: 3.0, tariff: 0.5,
  };
  score += supplyMap[mappedType] || 0;

  // 供应中断信号
  if (text.includes('supply') || text.includes('disrupt') || text.includes('shortage')) score += 1.0;

  return clamp(score, 0, 10);
}

// ─────────────────────────────────────────────────
// D3 价格影响 (0-10)
// ─────────────────────────────────────────────────
export function scoreD3(event) {
  let score = 2.0;
  const text = ((event.title || '') + ' ' + (event.description || '')).toLowerCase();

  // 商品波动性权重（基于历史特性）
  const volatilityMap = {
    'oil': 3.0, 'gas': 2.8, 'lithium': 2.5, 'li': 2.5,
    'nickel': 2.3, 'ni': 2.3, 'copper': 2.0, 'cu': 2.0,
    'iron': 1.5, 'fe': 1.5, 'gold': 1.8, 'au': 1.8,
    'rare earth': 2.2, 'ree': 2.2, 'uranium': 2.0, 'cobalt': 2.0,
  };
  let maxVol = 0;
  for (const [mineral, vol] of Object.entries(volatilityMap)) {
    if (text.includes(mineral)) maxVol = Math.max(maxVol, vol);
  }
  score += maxVol;

  // 价格信号词
  const signalCount = PRICE_SIGNALS.filter(s => text.includes(s)).length;
  score += Math.min(signalCount * 0.8, 2.0);

  // 事件类型调整
  const mappedType = mapEventType(event);
  if (mappedType === 'war' || mappedType === 'conflict') score += 1.0;
  if (mappedType === 'export_control') score += 0.8;

  return clamp(score, 0, 10);
}

// ─────────────────────────────────────────────────
// D4 政策方向 (-5 到 +5，双极)
// ─────────────────────────────────────────────────
export function scoreD4(event) {
  let score = 0.0;
  const mappedType = mapEventType(event);

  // 风险事件（负分 = 保护主义方向）
  const riskEvents = {
    sanction: -3.0, export_control: -3.0, tariff: -2.0,
    embargo: -4.0, conflict: -3.0, shipping: -2.0, mine_closure: -2.0,
  };

  // 利好事件（正分 = 开放方向）
  const positiveEvents = {
    trade_agreement: 3.0, investment: 2.0,
  };

  if (mappedType in riskEvents) score = riskEvents[mappedType];
  else if (mappedType in positiveEvents) score = positiveEvents[mappedType];

  // 关键词微调
  const text = ((event.title || '') + ' ' + (event.description || '')).toLowerCase();
  if (text.includes('restrict') || text.includes('control')) score -= 0.5;
  if (text.includes('cooperat') || text.includes('partnership')) score += 0.5;
  if (text.includes('protectionis')) score -= 1.0;
  if (text.includes('liberali') || text.includes('free trade')) score += 1.0;

  return clamp(score, -5, 5);
}

// ─────────────────────────────────────────────────
// D5 持续性 (0-10)
// ─────────────────────────────────────────────────
export function scoreD5(event) {
  const mappedType = mapEventType(event);

  const durationMap = {
    conflict: 8.0, war: 9.0, sanction: 7.0,
    export_control: 6.0, tariff: 5.0, trade_agreement: 4.0,
    strike: 3.0, mine_closure: 4.0, shipping: 3.0,
    investment: 5.0, other: 3.0,
  };
  let score = durationMap[mappedType] || 3.0;

  // 关键词调整
  const text = ((event.title || '') + ' ' + (event.description || '')).toLowerCase();
  if (text.includes('long-term') || text.includes('permanent') || text.includes('structural')) score += 1.0;
  if (text.includes('temporary') || text.includes('brief') || text.includes('short-term')) score -= 1.0;
  if (text.includes('ongoing') || text.includes('persistent') || text.includes('chronic')) score += 0.5;

  return clamp(score, 0, 10);
}

// ─────────────────────────────────────────────────
// CRI 综合指数计算
// ─────────────────────────────────────────────────
export function calculateCRI(scores) {
  const d4Norm = Math.abs(scores.d4) * 2;
  const cri =
    WEIGHTS.d1 * scores.d1 +
    WEIGHTS.d2 * scores.d2 +
    WEIGHTS.d3 * scores.d3 +
    WEIGHTS.d4 * d4Norm +
    WEIGHTS.d5 * scores.d5;
  return Math.round(cri * 100) / 100;
}

// ─────────────────────────────────────────────────
// 风险等级 + 行动建议
// ─────────────────────────────────────────────────
export function getRiskLevel(cri) {
  if (cri >= 7.0) return { level: 'EXTREME', color: '#dc2626', action: 'CRITICAL', sla: '<4h' };
  if (cri >= 5.0) return { level: 'HIGH', color: '#f59e0b', action: 'Active Hedge', sla: '72h' };
  if (cri >= 3.0) return { level: 'MEDIUM', color: '#eab308', action: 'Attention', sla: '1 week' };
  return { level: 'LOW', color: '#10b981', action: 'Monitor', sla: 'Monthly' };
}

// ─────────────────────────────────────────────────
// 置信度计算
// ─────────────────────────────────────────────────
export function calculateConfidence(event) {
  let conf = 0.5; // 基础
  const desc = event.description || '';
  const title = event.title || '';

  // 描述长度加分（内容越丰富置信度越高）
  conf += Math.min(desc.length / 1000, 0.2);

  // 标题长度
  conf += Math.min(title.length / 200, 0.05);

  // 有来源 URL
  if (event.source_url && event.source_url.length > 20) conf += 0.1;

  // 高质量来源
  const url = (event.source_url || '').toLowerCase();
  if (SOURCE_QUALITY_HIGH.some(s => url.includes(s))) conf += 0.1;

  // 有国家信息
  if (event.countries && event.countries.length > 0) conf += 0.05;

  // 涉及矿种
  if (event.commodities && event.commodities.length > 0) conf += 0.05;

  return Math.round(Math.max(0.35, Math.min(0.98, conf)) * 100) / 100;
}

// ─────────────────────────────────────────────────
// 主入口：对单条事件评分
// ─────────────────────────────────────────────────
export function scoreEvent(event) {
  const d1 = scoreD1(event);
  const d2 = scoreD2(event);
  const d3 = scoreD3(event);
  const d4 = scoreD4(event);
  const d5 = scoreD5(event);
  const cri = calculateCRI({ d1, d2, d3, d4, d5 });
  const risk = getRiskLevel(cri);
  const confidence = calculateConfidence(event);

  return {
    d1: Math.round(d1 * 10) / 10,
    d2: Math.round(d2 * 10) / 10,
    d3: Math.round(d3 * 10) / 10,
    d4,
    d4_normalized: Math.abs(d4) * 2,
    d5: Math.round(d5 * 10) / 10,
    cri,
    risk_level: risk.level,
    risk_color: risk.color,
    action: risk.action,
    sla: risk.sla,
    confidence,
  };
}

// ─────────────────────────────────────────────────
// 批量评分 + 排序
// ─────────────────────────────────────────────────
export function scoreBatch(events) {
  return events
    .map(e => ({ ...e, cri_score: scoreEvent(e) }))
    .sort((a, b) => b.cri_score.cri - a.cri_score.cri);
}

// ─────────────────────────────────────────────────
// 辅助函数
// ─────────────────────────────────────────────────
function mapEventType(event) {
  const rawType = event.event_type || 'other';
  const text = ((event.title || '') + ' ' + (event.description || '')).toLowerCase();

  // 先用基础映射
  let mapped = TYPE_MAP[rawType] || rawType;

  // 关键词精细化
  if (WAR_KEYWORDS.some(kw => text.includes(kw))) mapped = 'war';
  else if (mapped === 'conflict' && CONFLICT_KEYWORDS.some(kw => text.includes(kw))) mapped = 'conflict';
  else if (SANCTION_KEYWORDS.some(kw => text.includes(kw))) mapped = 'sanction';
  else if (TARIFF_KEYWORDS.some(kw => text.includes(kw))) mapped = 'tariff';
  else if (AGREEMENT_KEYWORDS.some(kw => text.includes(kw))) mapped = 'trade_agreement';

  return mapped;
}

function clamp(val, min, max) {
  return Math.round(Math.max(min, Math.min(max, val)) * 10) / 10;
}
