// Simple data-fetching hook with manual refresh + optional polling interval.
import { useCallback, useEffect, useRef, useState } from "react";

export function useFetch<T>(fn: () => Promise<T>, deps: any[] = [], pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const mounted = useRef(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const res = await fnRef.current();
      if (mounted.current) {
        setData(res);
        setError(null);
      }
    } catch (e: any) {
      if (mounted.current) setError(e?.message || "Failed to load");
    } finally {
      if (mounted.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    setLoading(true);
    load();
    let timer: any;
    if (pollMs > 0) timer = setInterval(() => load(), pollMs);
    return () => {
      mounted.current = false;
      if (timer) clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const refresh = useCallback(() => load(true), [load]);

  return { data, error, loading, refreshing, refresh };
}
