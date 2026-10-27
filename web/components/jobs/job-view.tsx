"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { JobProgress, liveStatus } from "@/components/jobs/job-progress";
import { Button } from "@/components/ui/button";
import type { Job } from "@/lib/api";
import { useJobEvents } from "@/lib/client/use-job-events";

/** A running job, followed live; when it succeeds, its concept or search page takes over. */
export function JobView({ job }: { job: Job }) {
  const router = useRouter();
  const finished = job.status === "succeeded" || job.status === "failed";
  const stream = useJobEvents(finished ? null : job.job_id);
  const status = liveStatus(job, stream.progress, stream.result !== null, stream.error);
  const error =
    stream.error ??
    (job.error ? { type: "error" as const, ...job.error, message: job.error.message ?? "" } : null);

  useEffect(() => {
    if (!stream.result) return;
    const target =
      job.job_type === "concept"
        ? `/concepts/${stream.result.result_id}`
        : `/searches/${stream.result.result_id}`;
    const timer = setTimeout(() => router.replace(target), 600);
    return () => clearTimeout(timer);
  }, [stream.result, job.job_type, router]);

  return (
    <div className="flex flex-col gap-6">
      <JobProgress job={job} progress={stream.progress} status={status} error={error} />
      {status === "failed" && (
        <div className="flex gap-3">
          <Button asChild variant="outline">
            <Link href="/concepts">Back to the concepts</Link>
          </Button>
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Closing this page doesn&apos;t stop the job: it keeps running, and anyone asking for the
        same concept joins it. Come back to this address to pick its progress up again.
      </p>
    </div>
  );
}
