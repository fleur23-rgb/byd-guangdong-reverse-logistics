'use client';

import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, BatteryCharging, Check, CircleAlert, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';

type Params = {
  retiredTons: number;
  captureRate: number;
  reuseShare: number;
  collectionCapacity: number;
  collectionMin: number;
  collectionMax: number;
  minimumThroughput: number;
  selfBuildShare: number;
  processingCapacity: number;
  partnerCapacityShare: number;
  radiusFirst: number;
  radiusEchelon: number;
  radiusRecycle: number;
  distanceFirst: number;
  distanceEchelon: number;
  distanceRecycle: number;
  transportPrice: number;
  fixedSelf: number;
  fixedEntrusted: number;
  unitSelf: number;
  unitEntrusted: number;
  fixedEchelon: number;
  fixedRecycle: number;
  unitEchelon: number;
  unitRecycle: number;
  emergencyUnit: number;
  emergencyMaxShare: number;
};

type FieldKey = keyof Params;
type Field = { key: FieldKey; label: string; unit: string; min: number; max: number; step: number };

const NATIONAL: Params = {
  retiredTons: 100000, captureRate: 0.4, reuseShare: 0.35,
  collectionCapacity: 5000, collectionMin: 3, collectionMax: 30, minimumThroughput: 300,
  selfBuildShare: 0.5, processingCapacity: 12000, partnerCapacityShare: 0.5,
  radiusFirst: 180, radiusEchelon: 450, radiusRecycle: 650,
  distanceFirst: 110, distanceEchelon: 280, distanceRecycle: 380,
  transportPrice: 0.49, fixedSelf: 1200000, fixedEntrusted: 350000,
  unitSelf: 380, unitEntrusted: 560, fixedEchelon: 2200000, fixedRecycle: 4200000,
  unitEchelon: 1300, unitRecycle: 1800, emergencyUnit: 100000, emergencyMaxShare: 0.2,
};

const GUANGDONG: Params = {
  ...NATIONAL, retiredTons: 8791, collectionCapacity: 3000, collectionMin: 3, collectionMax: 10,
  selfBuildShare: 0.34, processingCapacity: 8000, radiusFirst: 150, radiusEchelon: 300,
  radiusRecycle: 400, distanceFirst: 90, distanceEchelon: 210, distanceRecycle: 260,
};

const FIELD_GROUPS: { id: string; index: string; title: string; note: string; fields: Field[] }[] = [
  { id: 'market', index: '01', title: '市场与回收规模', note: '决定进入企业合规网络的总量与去向。', fields: [
    { key: 'retiredTons', label: '预计退役电池量', unit: '吨 / 年', min: 100, max: 2000000, step: 100 },
    { key: 'captureRate', label: '企业承接率', unit: '%', min: 0.01, max: 1, step: 0.01 },
    { key: 'reuseShare', label: '梯次利用比例', unit: '%', min: 0, max: 1, step: 0.01 },
  ] },
  { id: 'network', index: '02', title: '节点与能力', note: '控制区域中心数量、组织方式和合作方能力。', fields: [
    { key: 'collectionCapacity', label: '单个区域中心能力', unit: '吨 / 年', min: 100, max: 50000, step: 100 },
    { key: 'collectionMin', label: '区域中心最少数量', unit: '个', min: 1, max: 100, step: 1 },
    { key: 'collectionMax', label: '区域中心最多数量', unit: '个', min: 1, max: 150, step: 1 },
    { key: 'minimumThroughput', label: '中心最低处理量', unit: '吨 / 年', min: 0, max: 5000, step: 50 },
    { key: 'selfBuildShare', label: '自建中心比例', unit: '%', min: 0, max: 1, step: 0.01 },
    { key: 'processingCapacity', label: '单个后端设施能力', unit: '吨 / 年', min: 500, max: 100000, step: 500 },
    { key: 'partnerCapacityShare', label: '合作方可用能力', unit: '%', min: 0.05, max: 1, step: 0.01 },
  ] },
  { id: 'distance', index: '03', title: '距离与运输', note: '服务半径是约束；平均距离用于估算吨公里。', fields: [
    { key: 'radiusFirst', label: '来源—区域中心半径', unit: '公里', min: 20, max: 1500, step: 10 },
    { key: 'radiusEchelon', label: '中心—梯次设施半径', unit: '公里', min: 20, max: 3000, step: 10 },
    { key: 'radiusRecycle', label: '中心—再生设施半径', unit: '公里', min: 20, max: 3000, step: 10 },
    { key: 'distanceFirst', label: '前段平均运输距离', unit: '公里', min: 1, max: 1500, step: 1 },
    { key: 'distanceEchelon', label: '梯次平均运输距离', unit: '公里', min: 1, max: 3000, step: 1 },
    { key: 'distanceRecycle', label: '再生平均运输距离', unit: '公里', min: 1, max: 3000, step: 1 },
    { key: 'transportPrice', label: '运输单价', unit: '元 / 吨·公里', min: 0.01, max: 10, step: 0.01 },
  ] },
  { id: 'cost', index: '04', title: '设施与作业成本', note: '所有金额均为年度化口径，可替换为当地报价。', fields: [
    { key: 'fixedSelf', label: '自建中心固定成本', unit: '元 / 个·年', min: 0, max: 20000000, step: 10000 },
    { key: 'fixedEntrusted', label: '委托中心固定成本', unit: '元 / 个·年', min: 0, max: 10000000, step: 10000 },
    { key: 'unitSelf', label: '自建中心单位作业费', unit: '元 / 吨', min: 0, max: 5000, step: 10 },
    { key: 'unitEntrusted', label: '委托中心单位作业费', unit: '元 / 吨', min: 0, max: 5000, step: 10 },
    { key: 'fixedEchelon', label: '梯次设施固定成本', unit: '元 / 个·年', min: 0, max: 50000000, step: 10000 },
    { key: 'fixedRecycle', label: '再生设施固定成本', unit: '元 / 个·年', min: 0, max: 50000000, step: 10000 },
    { key: 'unitEchelon', label: '梯次利用单位处理费', unit: '元 / 吨', min: 0, max: 10000, step: 10 },
    { key: 'unitRecycle', label: '再生利用单位处理费', unit: '元 / 吨', min: 0, max: 10000, step: 10 },
    { key: 'emergencyUnit', label: '应急外包单位成本', unit: '元 / 吨', min: 1000, max: 300000, step: 1000 },
    { key: 'emergencyMaxShare', label: '应急外包上限', unit: '%', min: 0, max: 1, step: 0.01 },
  ] },
];

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const money = (value: number) => value >= 100000000 ? `${(value / 100000000).toFixed(2)} 亿元` : `${(value / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 万元`;
const number = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 0 });
const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

function calculate(p: Params) {
  const intake = p.retiredTons * p.captureRate;
  const desiredCenters = Math.ceil(intake / Math.max(1, p.collectionCapacity));
  const centers = clamp(desiredCenters, Math.min(p.collectionMin, p.collectionMax), Math.max(p.collectionMin, p.collectionMax));
  const selfCenters = Math.round(centers * p.selfBuildShare);
  const entrustedCenters = centers - selfCenters;
  const firstReach = Math.min(1, p.radiusFirst / Math.max(1, p.distanceFirst));
  const echelonReach = Math.min(1, p.radiusEchelon / Math.max(1, p.distanceEchelon));
  const recycleReach = Math.min(1, p.radiusRecycle / Math.max(1, p.distanceRecycle));
  const collectionCapacity = centers * p.collectionCapacity * firstReach;
  const availableProcessing = p.processingCapacity * p.partnerCapacityShare;
  const echelonDemand = intake * p.reuseShare;
  const recycleDemand = intake * (1 - p.reuseShare);
  const echelonFacilities = Math.max(1, Math.ceil(echelonDemand / Math.max(1, availableProcessing)));
  const recycleFacilities = Math.max(1, Math.ceil(recycleDemand / Math.max(1, availableProcessing)));
  const processingCapacity = (echelonFacilities * availableProcessing * echelonReach) + (recycleFacilities * availableProcessing * recycleReach);
  const normal = Math.min(intake, collectionCapacity, processingCapacity);
  const emergency = Math.max(0, intake - normal);
  const emergencyShare = intake ? emergency / intake : 0;
  const fixedCollection = selfCenters * p.fixedSelf + entrustedCenters * p.fixedEntrusted;
  const variableCollection = normal * (p.selfBuildShare * p.unitSelf + (1 - p.selfBuildShare) * p.unitEntrusted);
  const fixedProcessing = echelonFacilities * p.fixedEchelon + recycleFacilities * p.fixedRecycle;
  const variableProcessing = normal * (p.reuseShare * p.unitEchelon + (1 - p.reuseShare) * p.unitRecycle);
  const avgSecondDistance = p.reuseShare * p.distanceEchelon + (1 - p.reuseShare) * p.distanceRecycle;
  const transport = normal * (p.distanceFirst + avgSecondDistance) * p.transportPrice;
  const emergencyCost = emergency * p.emergencyUnit;
  const costs = [
    { label: '区域中心固定成本', value: fixedCollection },
    { label: '区域中心作业成本', value: variableCollection },
    { label: '后端设施固定成本', value: fixedProcessing },
    { label: '梯次与再生处理', value: variableProcessing },
    { label: '运输成本', value: transport },
    { label: '应急外包', value: emergencyCost },
  ];
  const total = costs.reduce((sum, item) => sum + item.value, 0);
  return { intake, centers, selfCenters, entrustedCenters, echelonFacilities, recycleFacilities, normal, emergency, emergencyShare, costs, total, unitCost: intake ? total / intake : 0, feasible: emergencyShare <= p.emergencyMaxShare + 1e-9 };
}

function ParameterField({ field, value, onChange }: { field: Field; value: number; onChange: (value: number) => void }) {
  const isPercent = field.unit === '%';
  const shown = isPercent ? Math.round(value * 100) : value;
  const factor = isPercent ? 100 : 1;
  return <div className="parameter-field">
    <div className="field-head"><label htmlFor={field.key}>{field.label}</label><span>{field.unit}</span></div>
    <div className="field-control">
      <input className="range-input" type="range" value={value} min={field.min} max={field.max} step={field.step} onChange={(event) => onChange(Number(event.target.value))} aria-label={field.label} />
      <input id={field.key} type="number" value={shown} min={field.min * factor} max={field.max * factor} step={field.step * factor} onChange={(event) => onChange(clamp(Number(event.target.value) / factor, field.min, field.max))} />
    </div>
  </div>;
}

function NetworkFigure({ result, scope }: { result: ReturnType<typeof calculate>; scope: string }) {
  const collectionNodes = Array.from({ length: Math.min(9, result.centers) });
  return <div className="network-object" aria-label={`${scope}逆向物流网络示意图`}>
    <svg viewBox="0 0 520 520" role="img">
      <circle cx="260" cy="260" r="188" className="orbit outer" />
      <circle cx="260" cy="260" r="116" className="orbit" />
      {collectionNodes.map((_, index) => { const angle = (index / collectionNodes.length) * Math.PI * 2 - Math.PI / 2; const x = 260 + Math.cos(angle) * 188; const y = 260 + Math.sin(angle) * 188; return <g key={index}><line x1={x} y1={y} x2="260" y2="260" className="network-line" /><circle cx={x} cy={y} r="11" className="collection-node" /></g>; })}
      <path d="M260 168 L338 304 L182 304 Z" className="echelon-node" />
      <circle cx="260" cy="260" r="49" className="core-node" />
      <text x="260" y="252" textAnchor="middle">{result.centers}</text>
      <text x="260" y="278" textAnchor="middle" className="small-text">区域中心</text>
      <text x="260" y="498" textAnchor="middle" className="scope-text">{scope}</text>
    </svg>
    <span className="serial">NETWORK / {String(result.centers).padStart(2, '0')}</span>
  </div>;
}

export default function Home() {
  const [params, setParams] = useState<Params>(NATIONAL);
  const [scope, setScope] = useState('中国自定义区域');
  const [preset, setPreset] = useState<'custom' | 'guangdong'>('custom');
  const result = useMemo(() => calculate(params), [params]);
  const maxCost = Math.max(...result.costs.map((item) => item.value), 1);

  const setField = (key: FieldKey, value: number) => { setPreset('custom'); setParams((current) => ({ ...current, [key]: value })); };
  const loadGuangdong = () => { setParams(GUANGDONG); setScope('广东省 · 论文参考案例'); setPreset('guangdong'); };
  const loadNational = () => { setParams(NATIONAL); setScope('中国自定义区域'); setPreset('custom'); };

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const registration = context.registerTool({
      name: 'configure_reverse_logistics_model',
      title: '配置全国动力电池逆向物流模型',
      description: '修改项目范围和任意模型参数，网页会即时重新计算成本、能力缺口与建议节点数。',
      inputSchema: {
        type: 'object',
        properties: {
          scope: { type: 'string' },
          preset: { type: 'string', enum: ['national_template', 'guangdong_case'] },
          parameters: { type: 'object', additionalProperties: { type: 'number' } },
        },
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute(input: unknown) {
        const value = input as { scope?: string; preset?: string; parameters?: Record<string, number> };
        const base = value.preset === 'guangdong_case' ? GUANGDONG : NATIONAL;
        const validKeys = new Set(Object.keys(NATIONAL));
        const overrides = Object.fromEntries(Object.entries(value.parameters ?? {}).filter(([key, item]) => validKeys.has(key) && Number.isFinite(item)));
        const next = { ...base, ...overrides } as Params;
        setParams(next);
        if (value.scope) setScope(value.scope);
        setPreset(value.preset === 'guangdong_case' ? 'guangdong' : 'custom');
        const nextResult = calculate(next);
        return { scope: value.scope ?? scope, total_cost_yuan: nextResult.total, unit_cost_yuan_per_ton: nextResult.unitCost, collection_centers: nextResult.centers, emergency_share: nextResult.emergencyShare, feasible: nextResult.feasible };
      },
    }, { signal: lifecycle.signal });
    Promise.resolve(registration).catch(() => undefined);
    return () => lifecycle.abort();
  }, [scope]);

  return <main>
    <nav className="top-nav">
      <a className="wordmark" href="#top">REVERSE / CHINA</a>
      <div className="nav-links"><a href="#model">模型</a><a href="#parameters">参数</a><a href="#results">结果</a></div>
    </nav>

    <section className="hero" id="top">
      <div className="hero-copy">
        <span className="kicker">全国动力电池逆向物流网络 / 参数化决策模型</span>
        <h1>任何地区。<br />任何参数。<br />即时测算。</h1>
        <p>填入当地退役规模、节点能力、运输距离和成本，模型即刻重算。广东仅作为内置参考，不再限定模型边界。</p>
      </div>
      <div className="hero-figure"><NetworkFigure result={result} scope={scope} /></div>
      <div className="hero-output" id="model">
        <span className="kicker">当前项目范围</span>
        <input className="scope-input" value={scope} onChange={(event) => { setScope(event.target.value); setPreset('custom'); }} aria-label="项目范围" />
        <div className="preset-links"><button className={preset === 'guangdong' ? 'active' : ''} onClick={loadGuangdong}>载入广东案例</button><button onClick={loadNational}>全国空白模板</button></div>
        <div className="hero-metric"><span>年度总成本</span><strong>{money(result.total)}</strong></div>
        <div className="hero-metric"><span>建议区域中心</span><strong>{result.centers} 个</strong></div>
        <div className={`feasibility ${result.feasible ? 'ok' : 'warn'}`}>{result.feasible ? <Check /> : <CircleAlert />} {result.feasible ? '能力约束可接受' : '应急外包超过设定上限'}</div>
      </div>
      <a className="scroll-cue" href="#parameters"><ArrowDown /> 调节全部参数</a>
      <span className="edge-label">GENERAL MODEL / CN</span>
    </section>

    <section className="parameter-section" id="parameters">
      <header className="section-heading"><span className="kicker">完整输入层 / 所有关键参数均可编辑</span><h2>不是情景按钮。<br />是你的真实输入。</h2><p>滑动用于快速试算，右侧数字框用于精确填值。结果随每次修改自动更新。</p></header>
      <div className="parameter-groups">{FIELD_GROUPS.map((group) => <article className="parameter-group" key={group.id}><header><span>{group.index}</span><div><h3>{group.title}</h3><p>{group.note}</p></div></header><div className="fields">{group.fields.map((field) => <ParameterField key={field.key} field={field} value={params[field.key]} onChange={(value) => setField(field.key, value)} />)}</div></article>)}</div>
      <Button variant="outline" className="reset-all" onClick={loadNational}><RotateCcw /> 恢复全国模板</Button>
    </section>

    <section className="results-section" id="results">
      <header className="results-copy"><span className="kicker">即时输出 / {scope}</span><h2>网络应该<br />长成什么样。</h2><p>这一层把输入转成年度化成本、能力缺口和节点规模，适合前期规划与敏感性测试。</p></header>
      <div className="result-object"><NetworkFigure result={result} scope={scope} /></div>
      <div className="result-data">
        <div className="big-result"><span>进入合规网络</span><strong>{number(result.intake)} 吨</strong><small>承接率 {percent(params.captureRate)}</small></div>
        <div className="result-grid"><div><span>单位成本</span><strong>{number(result.unitCost)} 元 / 吨</strong></div><div><span>常规网络处理</span><strong>{number(result.normal)} 吨</strong></div><div><span>应急外包</span><strong>{number(result.emergency)} 吨</strong></div><div><span>外包比例</span><strong>{percent(result.emergencyShare)}</strong></div></div>
        <div className="node-line"><span>区域中心 {result.centers}</span><span>自建 {result.selfCenters}</span><span>委托 {result.entrustedCenters}</span><span>梯次 {result.echelonFacilities}</span><span>再生 {result.recycleFacilities}</span></div>
      </div>
    </section>

    <section className="cost-section">
      <div className="cost-title"><span className="kicker">成本结构 / 年度化口径</span><h2>{money(result.total)}</h2><p>总成本</p></div>
      <div className="cost-bars">{result.costs.map((item) => <div className="cost-row" key={item.label}><div><span>{item.label}</span><strong>{money(item.value)}</strong></div><div className="cost-track"><i style={{ width: `${(item.value / maxCost) * 100}%` }} /></div></div>)}</div>
    </section>

    <footer><p>全国通用的是参数结构与计算逻辑，不代表已内置全国各地实测数据库。广东案例来自论文口径；其他地区应替换为当地退役量、候选设施、道路距离与成本数据。</p><span>PLANNING MODEL / 2025 SINGLE PERIOD</span></footer>
  </main>;
}

declare global {
  interface Document {
    modelContext?: { registerTool: (tool: { name: string; title: string; description: string; inputSchema: object; annotations: { readOnlyHint: boolean; untrustedContentHint: boolean }; execute: (input: unknown) => unknown }, options?: { signal?: AbortSignal }) => void | Promise<void> };
  }
}
