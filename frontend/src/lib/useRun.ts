import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { STAGES, type RunDetail, type StageEvent, type StageName, type StageView } from "./types";

export interface RunState {
  run: RunDetail | null;
  /** Stage cards: latest live event per stage, falling back to the stored detail. */
  stages: StageView[];
  /** Every stage event in order (event log). */
  events: StageEvent[];
  /** True while the SSE stream is open and the run is not finished. */
  live: boolean;
  error: string | null;
  setRun: (run: RunDetail) => void;
}

function toView(ev: StageEvent): StageView {
  const duration = ev.payload["duration_ms"];
  return {
    stage: ev.stage,
    status: ev.status,
    message: ev.message,
    started_at: ev.started_at,
    ended_at: ev.ended_at,
    duration_ms: typeof duration === "number" ? duration : null,
    payload: ev.payload,
  };
}

/**
 * Loads a run and follows its SSE stream. Stage cards update from events as they arrive; the full
 * detail (rule results, explanation) is re-fetched after each finished stage so panels stay complete.
 */
export function useRun(runId: string): RunState {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetching = useRef(false);
  const again = useRef(false);

  const refresh = useCallback(async () => {
    if (fetching.current) {
      again.current = true;
      return;
    }
    fetching.current = true;
    try {
      do {
        again.current = false;
        setRun(await api.run(runId));
      } while (again.current);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      fetching.current = false;
    }
  }, [runId]);

  useEffect(() => {
    setRun(null);
    setEvents([]);
    setError(null);
    void refresh();

    const es = new EventSource(api.eventsUrl(runId));
    setLive(true);
    es.addEventListener("stage", (msg) => {
      const ev = JSON.parse((msg as MessageEvent<string>).data) as StageEvent;
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
      if (ev.status !== "RUNNING") void refresh();
    });
    es.addEventListener("end", () => {
      es.close(); // otherwise the browser reconnects when the server closes the stream
      setLive(false);
      void refresh();
    });
    es.onerror = () => {
      // The browser retries on its own (sending Last-Event-ID); only a closed stream is final.
      if (es.readyState === EventSource.CLOSED) {
        setLive(false);
        setError("Lost the live connection to the server. Reload to try again.");
      }
    };
    return () => es.close();
  }, [runId, refresh]);

  const stages = useMemo<StageView[]>(() => {
    const latest = new Map<StageName, StageEvent>();
    for (const ev of events) latest.set(ev.stage, ev);
    return STAGES.map((name) => {
      const ev = latest.get(name);
      if (ev) return toView(ev);
      return (
        run?.stages.find((s) => s.stage === name) ?? {
          stage: name,
          status: "PENDING",
          message: null,
          started_at: null,
          ended_at: null,
          duration_ms: null,
          payload: {},
        }
      );
    });
  }, [events, run]);

  return { run, stages, events, live, error, setRun };
}
