-- A search job carries its search's id in params. The API looks a search's latest job up by that
-- id for each search it returns (one search, or a page of the searches index).
CREATE INDEX IF NOT EXISTS ix_jobs_search_id
    ON msr.jobs ((params->>'search_id'), created_at)
    WHERE job_type = 'search';
