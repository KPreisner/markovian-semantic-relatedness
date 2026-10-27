-- Each concept records the job that built it, so the API can return that job's status, attempts,
-- warnings, and compute time with the concept. (jobs.result_id alone is ambiguous: a job that
-- finds the concept already cached also succeeds with it.) NULL for a concept stored without a
-- job, or once its job is deleted.
ALTER TABLE msr.concepts ADD COLUMN IF NOT EXISTS job_id uuid;
ALTER TABLE msr.concepts
    ADD CONSTRAINT fk_concepts_jobs FOREIGN KEY (job_id)
    REFERENCES msr.jobs (job_id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_concepts_job_id ON msr.concepts (job_id);

-- Concepts stored before this: the earliest job that succeeded with the concept built it (any
-- later one found it cached).
UPDATE msr.concepts AS c
SET job_id = j.job_id
FROM (
    SELECT DISTINCT ON (result_id) result_id, job_id
    FROM msr.jobs
    WHERE job_type = 'concept' AND status = 'succeeded'
    ORDER BY result_id, created_at
) AS j
WHERE j.result_id = c.concept_id AND c.job_id IS NULL;
