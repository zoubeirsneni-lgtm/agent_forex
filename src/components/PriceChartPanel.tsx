import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ForexPair, SupportResistanceInfo } from '../lib/forexEngine';

export interface PricePoint {
  time: string;
  price: number;
}

interface PriceChartPanelProps {
  pair: ForexPair;
  data: PricePoint[];
  supportResistance?: SupportResistanceInfo | null;
  isWait?: boolean;
}

export function PriceChartPanel({
  pair,
  data,
  supportResistance = null,
  isWait = false,
}: PriceChartPanelProps) {
  if (isWait || data.length === 0) return null;

  const digits = pair === 'USDJPYm' ? 3 : 5;
  const pip = pair === 'USDJPYm' ? 0.01 : 0.0001;
  const latestPrice = data[data.length - 1]?.price;
  const firstPrice = data[0]?.price;
  const isUp = latestPrice !== undefined && firstPrice !== undefined ? latestPrice >= firstPrice : true;
  const strokeColor = isUp ? '#10b981' : '#ef4444';

  let minP = Infinity;
  let maxP = -Infinity;
  for (const pt of data) {
    if (pt.price < minP) minP = pt.price;
    if (pt.price > maxP) maxP = pt.price;
  }
  const span = maxP - minP || pip;
  const support = supportResistance?.support ?? null;
  const resistance = supportResistance?.resistance ?? null;

  const showSupportLine =
    support !== null && support.price >= minP - span * 0.65 && support.price <= maxP + span * 0.65;
  const showResistanceLine =
    resistance !== null && resistance.price >= minP - span * 0.65 && resistance.price <= maxP + span * 0.65;

  let visMin = minP;
  let visMax = maxP;
  if (showSupportLine && support) {
    visMin = Math.min(visMin, support.price);
    visMax = Math.max(visMax, support.price);
  }
  if (showResistanceLine && resistance) {
    visMin = Math.min(visMin, resistance.price);
    visMax = Math.max(visMax, resistance.price);
  }
  const visSpan = visMax - visMin || pip;
  const domainMin = visMin - visSpan * 0.08;
  const domainMax = visMax + visSpan * 0.08;

  return (
    <section className="mt-6 rounded-xl border border-[#1e2633] bg-[#0f131a] p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-[#1e2633] pb-3">
        <div className="flex flex-wrap items-baseline gap-3">
          <h3 className="text-base font-bold text-slate-100">
            Prix en temps réel — {pair}
          </h3>
          <span className="text-xs font-medium text-slate-400">
            Bougies 30s ({data.length} points)
          </span>
        </div>
        <div className="flex flex-wrap items-baseline gap-3 font-mono text-xs tabular-nums">
          {support && (
            <span className="text-emerald-400">
              S {support.price.toFixed(digits)}
            </span>
          )}
          {resistance && (
            <span className="text-red-400">
              R {resistance.price.toFixed(digits)}
            </span>
          )}
          {latestPrice !== undefined && (
            <span className="text-sm font-bold text-slate-100">
              {latestPrice.toFixed(digits)}
            </span>
          )}
        </div>
      </div>

      <div className="h-56 w-full bg-transparent">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
            <CartesianGrid stroke="#1e2633" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
              tickLine={false}
              axisLine={{ stroke: '#1e2633' }}
              minTickGap={28}
            />
            <YAxis
              domain={[domainMin, domainMax]}
              stroke="#64748b"
              tick={{ fill: '#94a3b8', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
              tickLine={false}
              axisLine={false}
              width={digits === 3 ? 62 : 70}
              tickFormatter={(val: number) => val.toFixed(digits)}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#090c11',
                borderColor: '#1e2633',
                borderRadius: '8px',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '12px',
                color: '#f1f5f9',
              }}
              labelStyle={{ color: '#94a3b8', marginBottom: '2px' }}
              formatter={(value) => [Number(value).toFixed(digits), pair]}
            />
            {showSupportLine && support && (
              <ReferenceLine
                y={support.price}
                stroke="#10b981"
                strokeDasharray="4 4"
                strokeOpacity={0.85}
                label={{
                  value: `S ${support.price.toFixed(digits)}`,
                  position: 'insideBottomRight',
                  fill: '#34d399',
                  fontSize: 11,
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              />
            )}
            {showResistanceLine && resistance && (
              <ReferenceLine
                y={resistance.price}
                stroke="#ef4444"
                strokeDasharray="4 4"
                strokeOpacity={0.85}
                label={{
                  value: `R ${resistance.price.toFixed(digits)}`,
                  position: 'insideTopRight',
                  fill: '#f87171',
                  fontSize: 11,
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              />
            )}
            <Line
              type="monotone"
              dataKey="price"
              stroke={strokeColor}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              activeDot={{ r: 4, fill: strokeColor, stroke: '#0f131a', strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
