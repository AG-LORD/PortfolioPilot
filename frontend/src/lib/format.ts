export function formatCurrency(value: string | number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(roundsToZeroMoney(value) ? 0 : Number(value));
}

// Prices and money always show exactly 2 decimals (₹735.60).
export function formatPrice(value: string | number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    // -0.001 would otherwise print as "-₹0.00".
  }).format(roundsToZeroMoney(value) ? 0 : Number(value));
}

// True when the amount shows as ₹0.00 (rounds to zero paise).
export function roundsToZeroMoney(value: string | number): boolean {
  return Math.abs(Number(value)) < 0.005;
}

// -1, 0 or 1 by the amount as displayed: tiny values that round to ₹0.00 are 0 (neutral colour, no sign).
export function moneySign(value: string | number): -1 | 0 | 1 {
  if (roundsToZeroMoney(value)) return 0;
  return Number(value) > 0 ? 1 : -1;
}

// Signed money for P&L: "+₹9,000.00" / "−₹120.50"; never "+₹0.00" or "−₹0.00".
export function formatSignedPrice(value: string | number): string {
  const sign = moneySign(value);
  return `${sign > 0 ? "+" : sign < 0 ? "−" : ""}${formatPrice(sign === 0 ? 0 : Math.abs(Number(value)))}`;
}

// Short rupee label for chart centres and axes: ₹85k, ₹1.5L, ₹2.3Cr.
export function formatCompactINR(value: string | number): string {
  const n = Number(value);
  const abs = Math.abs(n);
  const trim = (x: number) => (Math.round(x * 10) / 10).toString();
  if (abs >= 1e7) return `₹${trim(n / 1e7)}Cr`;
  if (abs >= 1e5) return `₹${trim(n / 1e5)}L`;
  if (abs >= 1e3) return `₹${Math.round(n / 1e3)}k`;
  return `₹${Math.round(n)}`;
}

// Whole-share quantities as integers (27, not 27.000000); fractional ones keep their digits.
export function formatShares(value: string | number): string {
  const n = Number(value);
  return Number.isInteger(n) ? n.toLocaleString("en-IN") : n.toLocaleString("en-IN", { maximumFractionDigits: 6 });
}

// Pass digits to fix the number of decimals shown; otherwise up to 2 are shown.
export function formatPercent(value: string | number, digits?: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "percent",
    minimumFractionDigits: digits ?? 0,
    maximumFractionDigits: digits ?? 2,
  }).format(Number(value));
}

export function formatSignedPercent(value: string | number, digits = 1): string {
  const n = Number(value);
  // Values that round to 0 at this precision show without a sign.
  const zero = Math.abs(n) < 0.5 / 10 ** (digits + 2);
  return `${zero ? "" : n > 0 ? "+" : "−"}${formatPercent(zero ? 0 : Math.abs(n), digits)}`;
}

export function formatDateTime(value: string | null): string {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

export function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value)) : "—";
}

// "27 Sep" for short labels.
export function formatShortDate(value: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(value));
}

// "today", "yesterday", "3 days ago", else the date.
export function formatRelativeDay(value: string | null, now: Date = new Date()): string {
  if (!value) return "—";
  const then = new Date(value);
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return formatDate(value);
}
