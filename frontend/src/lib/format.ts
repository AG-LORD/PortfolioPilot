export function formatCurrency(value: string | number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function formatPercent(value: string | number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "percent",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value)) : "—";
}
