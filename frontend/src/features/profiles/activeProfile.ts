import { useCallback, useSyncExternalStore } from "react";

// The active profile is shared by every page and survives reloads. It is only an id: pages
// always load that profile's data from the API, so switching never mixes records.
const KEY = "careerflow.activeProfile";
const listeners = new Set<() => void>();

function read(): string {
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

function write(id: string) {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    /* private mode: stay in memory only */
  }
  listeners.forEach((notify) => notify());
}

export function useActiveProfileId(): [string, (next: string | ((current: string) => string)) => void] {
  const id = useSyncExternalStore(
    (notify) => {
      listeners.add(notify);
      return () => listeners.delete(notify);
    },
    read,
    () => "",
  );
  const set = useCallback((next: string | ((current: string) => string)) => {
    const value = typeof next === "function" ? next(read()) : next;
    if (value !== read()) write(value);
  }, []);
  return [id, set];
}

/** Keep the saved id only if that profile still exists; otherwise fall back to the first. */
export function resolveActive(current: string, ids: string[]): string {
  return ids.includes(current) ? current : (ids[0] ?? "");
}
