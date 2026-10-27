// API bodies that pass the generated schemas.
import type { ConceptStatus, Job } from "@/lib/api";

export const JOB_ID = "01a17a3a-bd15-7212-9a8f-ef2486699bcf";
export const CONCEPT_ID = "01a17a3a-d46b-72dd-aa6c-961d31ff8d8f";

export function job(fields: Partial<Job> = {}): Job {
  return {
    job_id: JOB_ID,
    job_type: "concept",
    status: "queued",
    model_id: "simplewiki-small",
    params: { steps: 100 },
    progress: null,
    result_id: null,
    error: null,
    attempts: 0,
    warnings: [],
    created_at: "2026-10-26T22:00:00Z",
    started_at: null,
    finished_at: null,
    compute_seconds: null,
    ...fields,
  };
}

export function pending(): ConceptStatus {
  return { status: "pending", concept_id: null, job_id: JOB_ID, job: job() };
}
