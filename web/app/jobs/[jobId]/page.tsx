import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { JobView } from "@/components/jobs/job-view";
import { PageHeader } from "@/components/site/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { zGetJobResponse } from "@/lib/api/zod.gen";
import { load } from "@/lib/server/data";

export const metadata: Metadata = { title: "Job" };

export default function JobPage({ params }: PageProps<"/jobs/[jobId]">) {
  return (
    <Suspense fallback={<JobSkeleton />}>
      <JobContent params={params} />
    </Suspense>
  );
}

async function JobContent({ params }: { params: PageProps<"/jobs/[jobId]">["params"] }) {
  const { jobId } = await params;
  const job = await load(`/jobs/${encodeURIComponent(jobId)}`, zGetJobResponse);
  if (job.status === "succeeded" && job.result_id) {
    redirect(
      job.job_type === "concept" ? `/concepts/${job.result_id}` : `/searches/${job.result_id}`,
    );
  }
  const what = job.job_type === "concept" ? (job.root?.term ?? "a concept") : "a search";
  return (
    <>
      <PageHeader
        eyebrow={`${job.job_type} job · ${job.model_id}`}
        title={
          <>
            {job.job_type === "concept" ? "Walking from " : "Running "}
            <span className="text-gradient font-mono">{what}</span>
          </>
        }
        lead={
          job.job_type === "concept"
            ? "A worker walks the co-occurrence graph from the root, then scores every term against the reference terms."
            : "A worker scans the corpus for the concepts' terms, paragraph by paragraph."
        }
      />
      <div className="mx-auto w-full max-w-4xl px-4 py-10">
        <JobView job={job} />
      </div>
    </>
  );
}

function JobSkeleton() {
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-16">
      <Skeleton className="h-48 rounded-3xl" />
    </div>
  );
}
