/** Formatting shared by the valuation screens (design brief §4). */

export const aed = (n: number | string | null | undefined): string =>
  n === null || n === undefined || n === "" ? "—" : "AED " + Number(n).toLocaleString("en-US");

const ONES = [
  "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
  "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
  "Eighteen", "Nineteen",
];
const TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];

function underThousand(n: number): string {
  let s = "";
  if (n >= 100) {
    s += ONES[Math.floor(n / 100)] + " Hundred";
    n %= 100;
    if (n) s += " and ";
  }
  if (n >= 20) s += TENS[Math.floor(n / 10)] + (n % 10 ? "-" + ONES[n % 10] : "");
  else if (n) s += ONES[n];
  return s;
}

function wholeInWords(n: number): string {
  if (!n) return "Zero";
  const parts: string[] = [];
  const m = Math.floor(n / 1e6);
  const k = Math.floor((n % 1e6) / 1e3);
  const r = n % 1e3;
  if (m) parts.push(underThousand(m) + " Million");
  if (k) parts.push(underThousand(k) + " Thousand");
  if (r) parts.push(underThousand(r));
  return parts.join(" ");
}

/**
 * Live preview of the value in words while the valuer types.
 *
 * Must agree with the server (apps/jobs/calculations.py `amount_in_words`),
 * which is what actually goes on the signed report: a fractional amount
 * renders down to fils rather than rounding to a different whole number of
 * dirhams, so the words can never contradict the figures.
 */
export function inWords(amount: number | string | null | undefined): string {
  if (amount === null || amount === undefined || amount === "") return "";
  const value = Math.round(Number(amount) * 100) / 100;
  if (Number.isNaN(value)) return "";
  if (value < 0) return "";

  const dirhams = Math.floor(value);
  const fils = Math.round((value - dirhams) * 100);

  const unit = dirhams === 1 ? "Dirham" : "Dirhams";
  let words = `${wholeInWords(dirhams)} UAE ${unit}`;
  if (fils) words += ` and ${wholeInWords(fils)} Fils`;
  return words;
}

export const SQFT_PER_SQM = 10.76391;

export const toSqft = (sqm: number | string | null | undefined): number | null => {
  if (sqm === null || sqm === undefined || sqm === "") return null;
  const n = Number(sqm);
  return Number.isNaN(n) ? null : Math.round(n * SQFT_PER_SQM * 100) / 100;
};

/** `48.20 sqm (519 sqft)` (CLAUDE.md §2). */
export function formatArea(sqm: number | string | null | undefined): string {
  const sqft = toSqft(sqm);
  if (sqft === null) return "Not Applicable";
  return `${Number(sqm).toFixed(2)} sqm (${Math.round(sqft)} sqft)`;
}

/** `26 Aug 2026` (design brief §4). */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  // A date-only string ("2026-08-26") is a calendar day, not an instant:
  // `new Date()` would read it as UTC midnight and show the previous day to
  // anyone west of Greenwich.
  const dateOnly = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
  const d = dateOnly
    ? new Date(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1, Number(value.slice(8, 10)))
    : typeof value === "string"
      ? new Date(value)
      : value;
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "—";
  return (
    formatDate(d) +
    ", " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false })
  );
}
