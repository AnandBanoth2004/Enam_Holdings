"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const points = [
  { date: "04 Nov", value: 12.51 },
  { date: "05 Nov", value: 12.47 },
  { date: "06 Nov", value: 12.63 },
  { date: "07 Nov", value: 12.59 },
  { date: "10 Nov", value: 12.84 },
];

function formatCrore(value: number) {
  return `₹${value.toFixed(2)} Cr`;
}

export function MarketChart() {
  return (
    <div aria-label="Illustrative portfolio value chart" className="h-[184px] w-full sm:h-[210px]" role="img">
      <ResponsiveContainer height="100%" width="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="portfolio-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#173b57" stopOpacity={0.12} />
              <stop offset="100%" stopColor="#173b57" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e8edf1" strokeDasharray="3 4" vertical={false} />
          <XAxis
            axisLine={false}
            dataKey="date"
            tick={{ fill: "#788695", fontSize: 10 }}
            tickLine={false}
            tickMargin={10}
          />
          <YAxis
            axisLine={false}
            domain={["dataMin - 0.12", "dataMax + 0.12"]}
            tick={{ fill: "#788695", fontSize: 10 }}
            tickFormatter={(value: number) => value.toFixed(1)}
            tickLine={false}
            tickMargin={8}
            width={38}
          />
          <Tooltip
            contentStyle={{
              border: "1px solid #dce3e9",
              borderRadius: 8,
              boxShadow: "none",
              fontSize: 12,
            }}
            formatter={(value) => [formatCrore(Number(value)), "Portfolio value"]}
            labelStyle={{ color: "#526171", marginBottom: 4 }}
          />
          <Area
            activeDot={{ fill: "#173b57", r: 4, stroke: "#fff", strokeWidth: 2 }}
            dataKey="value"
            fill="url(#portfolio-fill)"
            stroke="#173b57"
            strokeWidth={2}
            type="monotone"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
