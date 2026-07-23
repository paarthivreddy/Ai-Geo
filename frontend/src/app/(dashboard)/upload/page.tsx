"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useRouter } from "next/navigation";
import { Upload, FileText, Loader2, CheckCircle, X, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface ColumnInfo {
  name: string;
  dtype: string;
  null_pct: number;
  distinct_count: number;
  sample_values: string[];
  min_length: number;
  max_length: number;
  pattern_regex: string | null;
}

interface UploadResponse {
  file_id: string;
  filename: string;
  size_bytes: number;
  row_count: number;
  column_count: number;
  columns: ColumnInfo[];
  detected_address_columns: string[];
}

const ADDRESS_FIELDS = [
  { key: "patient_id", label: "Patient ID" },
  { key: "address_line_1", label: "Address Line 1" },
  { key: "address_line_2", label: "Address Line 2" },
  { key: "landmark", label: "Landmark" },
  { key: "pincode", label: "PIN Code" },
  { key: "city", label: "City" },
  { key: "district", label: "District" },
  { key: "state", label: "State" },
  { key: "country", label: "Country" },
];

export default function UploadPage() {
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);
  const [profile, setProfile] = useState<UploadResponse | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({});
  const [isCreatingJob, setIsCreatingJob] = useState(false);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await api.post<UploadResponse>("/files/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setProfile(response.data);

      // Auto-map detected columns
      const autoMapping: Record<string, string> = {};
      response.data.detected_address_columns.forEach((col) => {
        const field = ADDRESS_FIELDS.find((f) => f.key.replace("_", " ").toLowerCase() === col.toLowerCase());
        if (field) autoMapping[field.key] = col;
      });
      setColumnMapping(autoMapping);

      toast.success("File uploaded and profiled successfully!");
    } catch (error) {
      toast.error("Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.ms-excel": [".xls"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
    maxSize: 2 * 1024 * 1024 * 1024, // 2GB
    noClick: isUploading,
  });

  const handleMappingChange = (fieldKey: string, columnName: string) => {
    setColumnMapping((prev) => ({ ...prev, [fieldKey]: columnName }));
  };

  const handleCreateJob = async () => {
    if (!profile) return;

    setIsCreatingJob(true);
    try {
      const mapping = Object.fromEntries(
        Object.entries(columnMapping).filter(([, v]) => v)
      );

      const response = await api.post("/files/" + profile.file_id + "/confirm-columns", {
        column_mapping: mapping,
        chunk_size: 50000,
      });

      toast.success("Processing job created!");
      router.push(`/jobs/${response.data.job_id}`);
    } catch (error) {
      toast.error("Failed to create job. Please check column mapping.");
    } finally {
      setIsCreatingJob(false);
    }
  };

  if (!profile) {
    return (
      <div className="container mx-auto px-4 py-12 max-w-3xl">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold">Upload Patient Data</h1>
          <p className="text-muted-foreground mt-2">
            Upload CSV or Excel files with patient addresses for enrichment
          </p>
        </div>

        <div
          {...getRootProps()}
          className={cn(
            "relative border-2 border-dashed rounded-xl p-12 transition-colors",
            isDragActive
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-primary/50"
          )}
        >
          <input {...getInputProps()} />
          <div className="text-center">
            <Upload className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-lg font-medium">
              {isDragActive ? "Drop the file here..." : "Drag & drop CSV/Excel file, or click to select"}
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Supports CSV, XLS, XLSX up to 2GB
            </p>
            {isUploading && (
              <div className="mt-4 flex items-center justify-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Uploading and profiling...</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* File Info */}
      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                {profile.filename}
              </CardTitle>
              <CardDescription>
                {profile.row_count.toLocaleString()} rows × {profile.column_count} columns •
                {profile.detected_address_columns.length} address columns detected
              </CardDescription>
            </div>
            <Button variant="outline" onClick={() => window.location.reload()}>
              <X className="h-4 w-4 mr-2" />
              Upload New File
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div className="p-3 bg-muted/50 rounded">
              <span className="text-muted-foreground">File Size</span>
              <div className="font-mono font-medium">
                {(profile.size_bytes / 1024 / 1024).toFixed(1)} MB
              </div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <span className="text-muted-foreground">Rows</span>
              <div className="font-mono font-medium">{profile.row_count.toLocaleString()}</div>
            </div>
            <div className="p-3 bg-muted/50 rounded">
              <span className="text-muted-foreground">Columns</span>
              <div className="font-mono font-medium">{profile.column_count}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Column Mapping */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Column Mapping</CardTitle>
          <CardDescription>
            Map your columns to address fields. Detected address columns are pre-selected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {ADDRESS_FIELDS.map((field) => (
              <div key={field.key} className="space-y-1">
                <Label htmlFor={field.key}>{field.label}</Label>
                <Select
                  value={columnMapping[field.key] || ""}
                  onValueChange={(value) => handleMappingChange(field.key, value)}
                >
                  <SelectTrigger id={field.key}>
                    <SelectValue placeholder="Select column..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">— Not mapped —</SelectItem>
                    {profile.columns.map((col) => (
                      <SelectItem
                        key={col.name}
                        value={col.name}
                        className={cn(
                          columnMapping[field.key] === col.name && "bg-primary/10"
                        )}
                      >
                        {col.name}
                        {profile.detected_address_columns.includes(col.name) && (
                          <CheckCircle className="h-4 w-4 ml-2 text-green-500" />
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Column Profiles */}
      <Card>
        <CardHeader>
          <CardTitle>Column Profiles</CardTitle>
          <CardDescription>Sample statistics for each column</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-2 pr-4">Column</th>
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Null %</th>
                  <th className="pb-2 pr-4">Distinct</th>
                  <th className="pb-2 pr-4">Sample Values</th>
                  <th className="pb-2 pr-4">Address?</th>
                </tr>
              </thead>
              <tbody>
                {profile.columns.map((col) => (
                  <tr key={col.name} className="border-b">
                    <td className="py-2 pr-4 font-mono">{col.name}</td>
                    <td className="py-2 pr-4">{col.dtype}</td>
                    <td className="py-2 pr-4">{col.null_pct.toFixed(1)}%</td>
                    <td className="py-2 pr-4">{col.distinct_count.toLocaleString()}</td>
                    <td className="py-2 pr-4">
                      <span className="text-muted-foreground">
                        {col.sample_values.slice(0, 3).join(", ")}
                        {col.sample_values.length > 3 && "..."}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      {profile.detected_address_columns.includes(col.name) && (
                        <span className="inline-flex items-center gap-1 text-green-600 bg-green-50 px-2 py-0.5 rounded text-xs">
                          <CheckCircle className="h-3 w-3" />
                          Detected
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Create Job */}
      <div className="mt-6 flex justify-end">
        <Button
          size="lg"
          onClick={handleCreateJob}
          disabled={isCreatingJob || Object.values(columnMapping).every((v) => !v)}
          className="gap-2"
        >
          {isCreatingJob ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Creating Job...
            </>
          ) : (
            <>
              <ChevronRight className="h-4 w-4" />
              Create Processing Job
            </>
          )}
        </Button>
      </div>
    </div>
  );
}