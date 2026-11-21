const int = new Intl.NumberFormat("en-US");

export const fmtInt = (n: number | null | undefined) => (n == null ? "Not available" : int.format(n));
export const fmtPct = (n: number | null | undefined) => (n == null ? "Not available" : `${n.toFixed(1)}%`);
export const fmtBytes = (n: number | null | undefined) => {
  if (n == null) return "";
  if (n < 1e6) return `${(n / 1e3).toFixed(0)} KB`;
  return `${(n / 1e6).toFixed(1)} MB`;
};
export const fmtDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "";
