export function formatCurrency(value: string | number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

// Pass digits to fix the number of decimals shown; otherwise up to 2 are shown.
export function formatPercent(value: string | number, digits?: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "percent",
    minimumFractionDigits: digits ?? 0,
    maximumFractionDigits: digits ?? 2,
  }).format(Number(value));
}

export function formatDateTime(value: string | null): string {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

export function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value)) : "—";
}
