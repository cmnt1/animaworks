/** Poll the selected Anima's session list as a slow recovery path. */

export const SESSION_REFRESH_INTERVAL_MS = 60_000;

export function startSessionsRefreshFallback(refresh, timers = {}) {
  const setIntervalFn = timers.setInterval || ((fn, ms) => globalThis.setInterval(fn, ms));
  const clearIntervalFn = timers.clearInterval || ((id) => globalThis.clearInterval(id));
  const timer = setIntervalFn(refresh, SESSION_REFRESH_INTERVAL_MS);
  return () => clearIntervalFn(timer);
}
