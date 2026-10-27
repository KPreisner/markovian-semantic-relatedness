"use client";

import { useEffect, useState } from "react";

import type { ErrorEvent, JobEvent, ProgressEvent, ResultEvent } from "@/lib/api";

export type JobStream = {
  progress: ProgressEvent | null;
  result: ResultEvent | null;
  error: ErrorEvent | null;
  /** The stream is open (false while connecting or reconnecting). */
  live: boolean;
};

/** A job's progress from the BFF's SSE relay. EventSource reconnects on its own and resumes from
 * the last event id; the stream is closed once the job's result or error arrives. */
export function useJobEvents(jobId: string | null): JobStream {
  const [state, setState] = useState<JobStream>({
    progress: null,
    result: null,
    error: null,
    live: false,
  });

  useEffect(() => {
    if (!jobId) return;
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    source.onopen = () => setState((s) => ({ ...s, live: true }));
    source.onerror = () => setState((s) => ({ ...s, live: false }));
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as JobEvent;
      if (event.type === "progress") setState((s) => ({ ...s, progress: event }));
      else {
        source.close();
        setState((s) => ({
          ...s,
          live: false,
          result: event.type === "result" ? event : s.result,
          error: event.type === "error" ? event : s.error,
        }));
      }
    };
    return () => source.close();
  }, [jobId]);

  return state;
}
