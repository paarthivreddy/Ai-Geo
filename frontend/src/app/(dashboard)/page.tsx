"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FileText, TrendingUp, CheckCircle, AlertCircle, MapPin } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

interface KPIMetrics {
  total_records: number;
  processed_records: number;
  pending_records: number;
  failed_records: number;
  manual_review_records: number;
  success_rate: number;
  data_quality_score: number;
  avg_confidence: number;
  total_processing_time_seconds: number;
}

interface QualityComparison {
  before: Record<string, number>;
  after: Record<string, number>;
  delta: Record<string, number>;
}

interface ConfidenceDistribution {
  high: number;
  medium: number;
  low: number;
  unverified: number;
}

interface StateDistribution {
  state: string;
  record_count: number;
  percentage: number;
}

interface ProcessingPerformance {
  date: string;
  jobs_processed: number;
  records_processed: number;
  avg_records_per_second: number;
  avg_processing_time_seconds: number;
}

export default function DashboardPage() {
  const { data: kpi, isLoading: kpiLoading } = useQuery<KPIMetrics>({
    queryKey: ["kpi"],
    queryFn: async () => {
      const res = await api.get("/dashboard/overview");
      return res.data;
    },
    refetchInterval: 30000,
  });

  const { data: quality } = useQuery<QualityComparison>({
    queryKey: ["quality"],
    queryFn: async () => {
      const res = await api.get("/dashboard/quality");
      return res.data;
    },
  });

  const { data: confidence } = useQuery<ConfidenceDistribution>({
    queryKey: ["confidence"],
    queryFn: async () => {
      const res = await api.get("/dashboard/confidence");
      return res.data;
    },
  });

  const { data: states } = useQuery<StateDistribution[]>({
    queryKey: ["states"],
    queryFn: async () => {
      const res = await api.get("/dashboard/geography/states");
      return res.data;
    },
  });

  const { data: _performance } = useQuery<ProcessingPerformance[]>({
    queryKey: ["performance"],
    queryFn: async () => {
      const res = await api.get("/dashboard/performance");
      return res.data;
    },
  });

  const { data: recentJobs } = useQuery({
    queryKey: ["recentJobs"],
    queryFn: async () => {
      const res = await api.get("/dashboard/jobs/recent");
      return res.data;
    },
  });

  if (kpiLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="h-4 bg-muted animate-pulse rounded w-3/4 mb-2" />
                <div className="h-8 bg-muted animate-pulse rounded w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">Overview of your address processing pipeline</p>
        </div>
        <Link href="/upload">
          <Button>
            <FileText className="mr-2 h-4 w-4" />
            Upload Data
          </Button>
        </Link>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Records</CardTitle>
            <MapPin className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{kpi?.total_records.toLocaleString() || 0}</div>
            <p className="text-xs text-muted-foreground">
              {kpi?.processed_records.toLocaleString() || 0} processed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {kpi?.success_rate.toFixed(1) || 0}%
            </div>
            <p className="text-xs text-muted-foreground">
              {kpi?.failed_records.toLocaleString() || 0} failed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Confidence</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-primary">
              {kpi?.avg_confidence.toFixed(1) || 0}%
            </div>
            <p className="text-xs text-muted-foreground">
              Quality: {kpi?.data_quality_score.toFixed(1) || 0}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Manual Review</CardTitle>
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-600">
              {kpi?.manual_review_records.toLocaleString() || 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {((kpi?.manual_review_records || 0) / (kpi?.processed_records || 1) * 100).toFixed(1)}% of processed
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {/* Quality Comparison */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Quality Improvement</CardTitle>
          </CardHeader>
          <CardContent>
            {quality && (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="p-4 bg-green-50 rounded-lg">
                    <p className="text-2xl font-bold text-green-700">
                      +{quality.delta.quality_improvement?.toFixed(1) || 0}%
                    </p>
                    <p className="text-xs text-muted-foreground">Quality Score</p>
                  </div>
                  <div className="p-4 bg-blue-50 rounded-lg">
                    <p className="text-2xl font-bold text-blue-700">
                      {quality.delta.fill_rate?.toFixed(1) || 0}%
                    </p>
                    <p className="text-xs text-muted-foreground">Fill Rate</p>
                  </div>
                  <div className="p-4 bg-purple-50 rounded-lg">
                    <p className="text-2xl font-bold text-purple-700">
                      {quality.after.improved_records?.toLocaleString() || 0}
                    </p>
                    <p className="text-xs text-muted-foreground">Records Improved</p>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Before</p>
                    <p className="font-medium">{quality.before.quality_pct?.toFixed(1) || 0}%</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">After</p>
                    <p className="font-medium text-green-600">
                      {quality.after.quality_pct?.toFixed(1) || 0}%
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Missing PIN</p>
                    <p className="font-medium">{quality.before.missing_pincode?.toLocaleString() || 0} → {quality.after.pincodes_added?.toLocaleString() || 0}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Missing City</p>
                    <p className="font-medium">{quality.before.missing_city?.toLocaleString() || 0} → {quality.after.cities_added?.toLocaleString() || 0}</p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Confidence Distribution */}
        <Card>
          <CardHeader>
            <CardTitle>Confidence Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {confidence && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge className="bg-green-100 text-green-800 w-20">HIGH</Badge>
                  <div className="flex-1 h-2 bg-muted rounded overflow-hidden">
                    <div
                      className="h-full bg-green-500"
                      style={{ width: `${((confidence.high || 0) / (confidence.high + confidence.medium + confidence.low + confidence.unverified || 1)) * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right font-mono">{confidence.high?.toLocaleString() || 0}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className="bg-yellow-100 text-yellow-800 w-20">MEDIUM</Badge>
                  <div className="flex-1 h-2 bg-muted rounded overflow-hidden">
                    <div
                      className="h-full bg-yellow-500"
                      style={{ width: `${((confidence.medium || 0) / (confidence.high + confidence.medium + confidence.low + confidence.unverified || 1)) * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right font-mono">{confidence.medium?.toLocaleString() || 0}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className="bg-orange-100 text-orange-800 w-20">LOW</Badge>
                  <div className="flex-1 h-2 bg-muted rounded overflow-hidden">
                    <div
                      className="h-full bg-orange-500"
                      style={{ width: `${((confidence.low || 0) / (confidence.high + confidence.medium + confidence.low + confidence.unverified || 1)) * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right font-mono">{confidence.low?.toLocaleString() || 0}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className="bg-gray-100 text-gray-800 w-20">UNVERIFIED</Badge>
                  <div className="flex-1 h-2 bg-muted rounded overflow-hidden">
                    <div
                      className="h-full bg-gray-400"
                      style={{ width: `${((confidence.unverified || 0) / (confidence.high + confidence.medium + confidence.low + confidence.unverified || 1)) * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right font-mono">{confidence.unverified?.toLocaleString() || 0}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top States */}
        <Card>
          <CardHeader>
            <CardTitle>Top States</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {states?.slice(0, 8).map((s) => (
                <div key={s.state} className="flex items-center justify-between">
                  <span className="text-sm">{s.state}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{s.record_count.toLocaleString()}</span>
                    <Badge variant="secondary" className="text-xs">
                      {s.percentage.toFixed(1)}%
                    </Badge>
                  </div>
                </div>
              ))}
            {(!states || states.length === 0) && (
              <p className="text-muted-foreground text-center py-4">No geographic data yet</p>
            )}
          </div>
        </CardContent>
        </Card>
      </div>

      {/* Recent Jobs */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Recent Jobs</CardTitle>
            <Link href="/jobs">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {recentJobs && recentJobs.length > 0 ? (
            <div className="space-y-3">
              {recentJobs.map((job: Record<string, unknown>) => (
                <Link
                  key={job.job_id as string}
                  href={`/jobs/${job.job_id}`}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <p className="font-medium truncate max-w-xs">
                        {job.filename as string}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(job.created_at as string).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <Badge
                      variant="secondary"
                      className={cn(
                        job.status === "completed" && "bg-green-100 text-green-800",
                        job.status === "processing" && "bg-blue-100 text-blue-800",
                        job.status === "failed" && "bg-red-100 text-red-800"
                      )}
                    >
                      {(job.status as string)?.replace("_", " ")}
                    </Badge>
                    <span className="text-muted-foreground">
                      {(job.processed_rows as number)?.toLocaleString()}/{(job.total_rows as number)?.toLocaleString()}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <FileText className="h-12 w-12 text-muted-foreground/50 mx-auto mb-3" />
              <p className="text-muted-foreground">No jobs yet. Upload a file to get started.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}