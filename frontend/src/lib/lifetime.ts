// Event lifetime helpers. Events are deleted EVENT_LIFETIME_HOURS after they are
// created (the backend enforces it; this is only used to explain it in the UI).

export const EVENT_LIFETIME_HOURS = 6;

/** The API sends UTC timestamps without a zone marker ("2026-11-12T18:00:00").
 *  `new Date()` would read those as *local* time, so pin them to UTC. */
export function parseUtc(iso: string): Date {
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

/** "5h 40m", "12 min" — time until `expiresAt`, or "a moment" once it has passed. */
export function timeLeftLabel(expiresAt: string, now: number = Date.now()): string {
  const ms = parseUtc(expiresAt).getTime() - now;
  if (ms <= 0) return "a moment";
  const mins = Math.ceil(ms / 60_000);
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

/** True when `expiresAt` is within `minutes` from now (and not yet past). */
export function endsWithin(expiresAt: string, minutes: number, now: number = Date.now()): boolean {
  const ms = parseUtc(expiresAt).getTime() - now;
  return ms > 0 && ms <= minutes * 60_000;
}
