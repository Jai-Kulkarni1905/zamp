import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Loads data and keeps it fresh without a dashboard-wide event stream:
 * every `fastMs` while `fast` is true (runs in progress), and whenever the tab becomes visible again.
 */
export function useAutoRefresh<T>(load: () => Promise<T>, deps: unknown[], opts: { fast?: boolean; fastMs?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);

  const run = useCallback(load, deps);

  const refresh = useCallback(async () => {
    const ticket = ++latest.current;
    try {
      const value = await run();
      if (ticket === latest.current) {
        setData(value);
        setError(null);
      }
    } catch (e) {
      if (ticket === latest.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  }, [run]);

  useEffect(() => {
    setLoading(true);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [refresh]);

  useEffect(() => {
    if (!opts.fast) return;
    const id = window.setInterval(() => void refresh(), opts.fastMs ?? 2000);
    return () => window.clearInterval(id);
  }, [opts.fast, opts.fastMs, refresh]);

  return { data, error, loading, refresh };
}
