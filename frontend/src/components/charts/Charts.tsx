"use client";

import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatPercent, formatPrice, formatShortDate } from "@/lib/format";

export const NOT_ENOUGH_HISTORY = "Not enough history yet: this chart appears after 2+ daily snapshots.";

const TOOLTIP_STYLE = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  color: "var(--popover-foreground)",
  fontSize: 12,
};
const TICK = { fill: "var(--muted-foreground)", fontSize: 11 };
// "dataMin - 2%" / "dataMax + 2%": recharts string domains only accept absolute
// offsets, so the 2% padding is expressed as functions. Never starts at 0.
const PADDED_DOMAIN: [(min: number) => number, (max: number) => number] = [(min) => min * 0.98, (max) => max * 1.02];

// Donut colours: chart-one (primary), chart-two, then hue-rotated variants of the
// primary for further stocks; cash always uses chart-cash.
const DERIVED_HUE_SHIFTS = [150, 250, 300, 60, 200, 110];
export function sliceColor(index: number): string {
  if (index === 0) return "var(--chart-one)";
  if (index === 1) return "var(--chart-two)";
  const shift = DERIVED_HUE_SHIFTS[(index - 2) % DERIVED_HUE_SHIFTS.length];
  const lighten = Math.floor((index - 2) / DERIVED_HUE_SHIFTS.length) % 2 === 0 ? 0 : 0.1;
  return `oklch(from var(--primary) calc(l + ${lighten}) c calc(h + ${shift}))`;
}
export const CASH_COLOR = "var(--chart-cash)";

export function ChartEmpty({ message = NOT_ENOUGH_HISTORY }: { message?: string }) {
  return (
    <div className="grid h-72 place-items-center rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export function ChartLegend({ items }: { items: Array<{ label: string; dashed?: boolean; color: string }> }) {
  return (
    <div className="mb-3 flex flex-wrap gap-5 text-xs">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-2">
          <svg width="20" height="2" aria-hidden="true">
            <line
              x1="0"
              x2="20"
              y1="1"
              y2="1"
              stroke={item.color}
              strokeWidth="2"
              strokeDasharray={item.dashed ? "5 5" : undefined}
            />
          </svg>
          {item.label}
        </span>
      ))}
    </div>
  );
}

type ComparePoint = { date: string; primary: number; benchmark: number | null };

// A portfolio / mix line against NIFTY 50 (dashed). Values are backend rupee amounts.
export function CompareLineChart({ data, primaryLabel }: { data: ComparePoint[]; primaryLabel: string }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tick={TICK}
            tickFormatter={(value: string) => formatShortDate(value)}
            minTickGap={32}
          />
          <YAxis
            width={56}
            tickLine={false}
            axisLine={false}
            tick={TICK}
            domain={PADDED_DOMAIN}
            tickFormatter={(value: number) => `₹${Math.round(value / 1000).toLocaleString("en-IN")}k`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(value) => formatShortDate(String(value))}
            formatter={(value) => formatPrice(Number(value))}
          />
          <Line
            type="monotone"
            name={primaryLabel}
            dataKey="primary"
            stroke="var(--primary)"
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            name="NIFTY 50"
            dataKey="benchmark"
            stroke="var(--chart-benchmark)"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export type DonutSlice = { name: string; weight: number; color: string };

export function Donut({ slices, centerLabel, centerValue }: { slices: DonutSlice[]; centerLabel: string; centerValue: string }) {
  return (
    <div className="relative h-56">
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={slices}
            dataKey="weight"
            nameKey="name"
            innerRadius={62}
            outerRadius={86}
            paddingAngle={2}
            stroke="none"
            isAnimationActive={false}
          >
            {slices.map((slice) => (
              <Cell key={slice.name} fill={slice.color} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value) => formatPercent(Number(value), 1)} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
        <div>
          <p className="text-xs text-muted-foreground">{centerLabel}</p>
          <p className="font-bold">{centerValue}</p>
        </div>
      </div>
    </div>
  );
}

export function DonutLegend({ slices }: { slices: DonutSlice[] }) {
  return (
    <ul className="space-y-3">
      {slices.map((slice) => (
        <li key={slice.name} className="flex items-center justify-between gap-3 text-sm">
          <span className="flex min-w-0 items-center gap-2">
            <i className="size-2.5 shrink-0 rounded-sm" style={{ background: slice.color }} aria-hidden="true" />
            <span className="truncate">{slice.name}</span>
          </span>
          <span className="font-semibold tabular-nums">{formatPercent(slice.weight, 1)}</span>
        </li>
      ))}
    </ul>
  );
}

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const gradientId = useId().replace(/:/g, "");
  if (values.length < 2) return null;
  const data = values.map((v, i) => ({ i, v }));
  return (
    <div className="h-12 w-28" role="img" aria-label={label}>
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Area
            type="monotone"
            dataKey="v"
            stroke="var(--primary)"
            fill={`url(#${gradientId})`}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PriceAreaChart({ points }: { points: Array<{ date: string; close: number }> }) {
  const gradientId = useId().replace(/:/g, "");
  return (
    <div className="h-44 rounded-lg border border-border bg-card p-2">
      <ResponsiveContainer>
        <AreaChart data={points}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" hide />
          <YAxis hide domain={PADDED_DOMAIN} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(value) => formatShortDate(String(value))}
            formatter={(value) => formatPrice(Number(value))}
          />
          <Area
            type="monotone"
            dataKey="close"
            name="Close"
            stroke="var(--primary)"
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
