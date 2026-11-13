import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ForexPair } from '../lib/forexEngine';

export interface PricePoint {
  time: string;
  price: number;
}

interface PriceChartPanelProps {
  pair: ForexPair;
  data: PricePoint[];
  isWait?: boolean;
}

export function PriceChartPanel({ pair, data, isWait = false }: PriceChartPanelProps) {
  if (isWait || data.length === 0) return null;

  const digits = pair === 'USDJPYm' ? 3 : 5;
  const latestPrice = data[data.length - 1]?.price;
  const firstPrice = data[0]?.price;
  const isUp = latestPrice !== undefined && firstPrice !== undefined ? latestPrice >= firstPrice : true;
  const strokeColor = isUp ? '#10b981' : '#ef4444';

  return (
    <section className="mt-6 rounded-xl border border-[#1e2633] bg-[#0f131a] p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-[#1e2633] pb-3">
        <div className="flex items-baseline gap-3">
          <h3 className="text-base font-bold text-slate-100">
            Prix en temps réel — {pair}
          </h3>
          <span className="text-xs font-medium text-slate-400">
            Bougies 30s ({data.length} points)
          </span>
        </div>
        {latestPrice !== undefined && (
          <div className="font-mono text-sm font-bold text-slate-100 tabular-nums">
            {latestPrice.toFixed(digits)}
          </div>
        )}
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
              domain={['auto', 'auto']}
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
