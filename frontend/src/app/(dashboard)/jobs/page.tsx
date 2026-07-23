"use client";

import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { ChevronRight, Loader2, CheckCircle, AlertCircle, Clock, FileText } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Job {
  job_id: string;
  filename: string;
  status: string;
  progress_pct: number;
  total_rows: number;
  processed_rows: number;
  succeeded_rows: number;
  failed_rows: number;
  manual_review_rows: number;
  total_chunks: number;
  completed_chunks: number[];
  failed_chunks: number[];
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

interface JobListResponse {
  jobs: Job[];
  total: number;
  limit: number;
  offset: number;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-100 text-green-800",
  processing: "bg-blue-100 text-blue-800",
  queued: "bg-yellow-100 text-yellow-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-100 text-gray-800",
  profiling: "bg-purple-100 text-purple-800",
  mapping: "bg-purple-100 text-purple-800",
  pending: "bg-gray-100 text-gray-800",
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  completed: <CheckCircle className="h-4 w-4" />,
  processing: <Loader2 className="h-4 w-4 animate-spin" />,
  queued: <Clock className="h-4 w-4" />,
  failed: <AlertCircle className="h-4 w-4" />,
  cancelled: <AlertCircle className="h-4 w-4" />,
  profiling: <Loader2 className="h-4 w-4 animate-spin" />,
  mapping: <Loader2 className="h-4 w-4 animate-spin" />,
  pending: <Clock className="h-4 w-4" />,
};

export default function JobsPage() {
  const { data, isLoading, error, refetch } = useQuery<JobListResponse>({
    queryKey: ["jobs"],
    queryFn: async () => {
      const response = await api.get("/jobs");
      return response.data;
    },
    refetchInterval: 5000,
  });

  const jobs = data?.jobs || [];

  const getStatusBadge = (status: string) => (
    <Badge variant="secondary" className={STATUS_COLORS[status] || STATUS_COLORS.pending}>
      {STATUS_ICONS[status] || <Clock className="h-3 w-3" />}
      <span className="capitalize ml-1">{status.replace("_", " ")}</span>
    </Badge>
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="max-w-md mx-auto">
        <CardContent className="pt-6 text-center">
          <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">Failed to load jobs</h3>
          <p className="text-muted-foreground mb-4">
            {error instanceof Error ? error.message : "Unknown error"}
          </p>
          <Button onClick={() => refetch()}>Retry</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Processing Jobs</h1>
          <p className="text-muted-foreground">
            {data?.total} {data?.total === 1 ? "job" : "jobs"} total
          </p>
        </div>
        <Link href="/upload">
          <Button>
            <FileText className="mr-2 h-4 w-4" />
            Upload New File
          </Button>
        </Link>
      </div>

      {jobs.length === 0 ? (
        <Card>
          <CardContent className="pt-12 text-center">
            <FileText className="h-16 w-16 text-muted-foreground/50 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No jobs yet</h3>
            <p className="text-muted-foreground mb-4">
              Upload a CSV or Excel file to start processing patient addresses.
            </p>
            <Link href="/upload">
              <Button>Upload First File</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => (
            <Link key={job.job_id} href={`/jobs/${job.job_id}`}>
              <Card className="hover:shadow-md transition-shadow cursor-pointer">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <CardTitle className="text-lg truncate">{job.filename}</CardTitle>
                      <p className="text-sm text-muted-foreground mt-1">
                        {format(new Date(job.created_at), "MMM d, yyyy HH:mm")}
                      </p>
                    </div>
                    {getStatusBadge(job.status)}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <p className="text-2xl font-bold">{job.total_rows.toLocaleString()}</p>
                      <p className="text-xs text-muted-foreground">Total Rows</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-primary">
                        {job.processed_rows.toLocaleString()}
                      </p>
                      <p className="text-xs text-muted-foreground">Processed</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-green-600">
                        {job.succeeded_rows.toLocaleString()}
                      </p>
                      <p className="text-xs text-muted-foreground">Succeeded</p>
                    </div>
                  </div>

                  {job.status === "processing" && (
                    <div>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span>Progress</span>
                        <span className="font-medium">{job.progress_pct.toFixed(1)}%</span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all duration-300"
                          style={{ width: `${job.progress_pct}%` }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        {job.completed_chunks.length} / {job.total_chunks} chunks
                      </p>
                    </div>
                  )}

                  {job.status === "completed" && (
                    <div className="grid grid-cols-3 gap-2 text-xs text-center pt-2 border-t">
                      <div className="text-green-600">
                        <p className="font-semibold">{job.succeeded_rows.toLocaleString()}</p>
                        <p className="text-muted-foreground">High Confidence</p>
                      </div>
                      <div className="text-yellow-600">
                        <p className="font-semibold">{job.manual_review_rows.toLocaleString()}</p>
                        <p className="text-muted-foreground">Needs Review</p>
                      </div>
                      {job.failed_rows > 0 && (
                        <div className="text-red-600">
                          <p className="font-semibold">{job.failed_rows.toLocaleString()}</p>
                          <p className="text-muted-foreground">Failed</p>
                        </div>
                      )}
                    </div>
                  )}

                  {job.status === "failed" && job.error_message && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
                      <p className="font-medium">Error:</p>
                      <p className="truncate">{job.error_message}</p>
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-2 border-t">
                    <span className="text-sm text-muted-foreground">
                      Chunks: {job.completed_chunks.length}/{job.total_chunks}
                    </span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}