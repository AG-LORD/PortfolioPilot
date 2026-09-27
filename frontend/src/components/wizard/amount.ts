const ONES = [
  "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
  "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
];
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

// Keeps digits and a single decimal point (max 2 decimals); returns a plain number string.
export function sanitizeAmount(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const [intPart, ...rest] = cleaned.split(".");
  const int = intPart.replace(/^0+(?=\d)/, "");
  return rest.length > 0 ? `${int}.${rest.join("").slice(0, 2)}` : int;
}

// Indian digit grouping (12,34,567) without converting through Number.
export function groupIndian(value: string): string {
  const [int, decimals] = value.split(".");
  let grouped = int;
  if (int.length > 3) {
    grouped = `${int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${int.slice(-3)}`;
  }
  return decimals !== undefined ? `${grouped}.${decimals}` : grouped;
}

function belowThousand(n: number): string {
  const parts: string[] = [];
  if (n >= 100) {
    parts.push(`${ONES[Math.floor(n / 100)]} hundred`);
    n %= 100;
  }
  if (n >= 20) {
    parts.push(n % 10 ? `${TENS[Math.floor(n / 10)]}-${ONES[n % 10]}` : TENS[Math.floor(n / 10)]);
  } else if (n > 0) {
    parts.push(ONES[n]);
  }
  return parts.join(" ");
}

function toWords(n: number): string {
  const parts: string[] = [];
  const crore = Math.floor(n / 10_000_000);
  const lakh = Math.floor((n % 10_000_000) / 100_000);
  const thousand = Math.floor((n % 100_000) / 1_000);
  const rest = n % 1_000;
  if (crore) parts.push(`${toWords(crore)} crore`);
  if (lakh) parts.push(`${belowThousand(lakh)} lakh`);
  if (thousand) parts.push(`${belowThousand(thousand)} thousand`);
  if (rest) parts.push(belowThousand(rest));
  return parts.join(" ");
}

// Only for lakh-and-above amounts, where the digit count is easy to misread.
export function amountInWords(value: string): string | null {
  const n = Math.floor(Number(value));
  if (!Number.isFinite(n) || n < 100_000) return null;
  const words = toWords(n);
  return `${words.charAt(0).toUpperCase()}${words.slice(1)} rupees`;
}
