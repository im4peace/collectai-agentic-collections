/**
 * Formats a UTC ISO-8601 timestamp as fixed Asia/Dubai local time ("GST",
 * UTC+4, no DST) for display. Mirrors the design mockups' `fmtDT` helper
 * (specs/design/mockups/E3-S4.html) so every screen renders timestamps the
 * same way. Not a general-purpose timezone library: the offset is a fixed
 * +4 hours because Gulf Standard Time never observes daylight saving.
 */
const GST_OFFSET_MS = 4 * 60 * 60 * 1000;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function formatDateTime(isoTimestamp: string | null | undefined): string {
  if (!isoTimestamp) {
    return "-";
  }
  const shifted = new Date(new Date(isoTimestamp).getTime() + GST_OFFSET_MS);
  const year = shifted.getUTCFullYear();
  const month = pad(shifted.getUTCMonth() + 1);
  const day = pad(shifted.getUTCDate());
  const hours = pad(shifted.getUTCHours());
  const minutes = pad(shifted.getUTCMinutes());
  return `${year}-${month}-${day} ${hours}:${minutes} GST`;
}
