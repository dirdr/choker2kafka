export function escapeHTML(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
}

export function formatTime(value, short = false) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Invalid recorded time";
  return (
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "UTC",
      ...(short ? {} : { day: "2-digit", month: "short" }),
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date) + (short ? "" : " UTC")
  );
}

export function rawInteger(value) {
  if (!Number.isSafeInteger(value)) return "Outside browser integer range";
  return String(value);
}

export function percent(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(1)}%`
    : "No data";
}

export function duration(value) {
  return typeof value === "number"
    ? `${(value / 1000).toFixed(1)}s`
    : "In progress";
}

export function statusClass(value) {
  if (
    [
      "healthy",
      "flowing",
      "completed",
      "resolved",
      "supported",
      "running",
    ].includes(value)
  )
    return "good";
  if (["failed", "violated", "error"].includes(value)) return "bad";
  return "warning";
}

export function label(value) {
  return String(value ?? "Unknown").replaceAll("_", " ");
}
