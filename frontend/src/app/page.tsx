import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight, Upload, BarChart2, FileText, Shield } from "lucide-react";

export default function HomePage() {
  return (
    <main className="min-h-screen">
      {/* Hero Section */}
      <section className="relative overflow-hidden py-20 lg:py-32">
        <div className="container mx-auto px-4">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
              GeoCare AI
              <span className="text-primary"> — India Patient Address Intelligence</span>
            </h1>
            <p className="mt-6 text-lg leading-8 text-muted-foreground">
              Enterprise-grade, offline-first platform for enriching, validating, and standardizing
              Indian patient addresses from healthcare datasets. Process up to 10M records with zero
              external API dependencies.
            </p>
            <div className="mt-10 flex items-center justify-center gap-4">
              <Link href="/upload">
                <Button size="lg" className="gap-2">
                  <Upload className="h-4 w-4" />
                  Upload & Process Data
                </Button>
              </Link>
              <Link href="/dashboard">
                <Button size="lg" variant="outline" className="gap-2">
                  View Dashboard
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-muted/50">
        <div className="container mx-auto px-4">
          <div className="mx-auto max-w-2xl text-center mb-16">
            <h2 className="text-3xl font-bold tracking-tight">Key Capabilities</h2>
            <p className="mt-4 text-muted-foreground">
              Built for healthcare organizations handling Indian patient data at scale
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Upload className="h-6 w-6 text-primary" />
                </div>
                <CardTitle className="mt-4">Data Ingestion</CardTitle>
                <CardDescription>
                  CSV/Excel upload up to 2GB, auto-detects address columns, profiles data quality
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Shield className="h-6 w-6 text-primary" />
                </div>
                <CardTitle className="mt-4">Address Enrichment</CardTitle>
                <CardDescription>
                  PIN code resolution, locality fuzzy matching, city/district/state hierarchy completion
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                  <FileText className="h-6 w-6 text-primary" />
                </div>
                <CardTitle className="mt-4">Confidence Scoring</CardTitle>
                <CardDescription>
                  Weighted 0-100 scores with HIGH/MEDIUM/LOW/UNVERIFIED tiers for review prioritization
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                  <BarChart2 className="h-6 w-6 text-primary" />
                </div>
                <CardTitle className="mt-4">Analytics Dashboard</CardTitle>
                <CardDescription>
                  Geographic heatmaps, quality trends, before/after comparison, export capabilities
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* Technical Highlights */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="mx-auto max-w-2xl text-center mb-16">
            <h2 className="text-3xl font-bold tracking-tight">Built for Scale & Compliance</h2>
            <p className="mt-4 text-muted-foreground">
              Architecture designed for healthcare data requirements
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <div className="p-6 rounded-xl border">
              <h3 className="text-xl font-semibold mb-2">Offline-First</h3>
              <p className="text-muted-foreground">
                All geography data pre-loaded. Zero external API calls during processing. Air-gapped
                deployment supported.
              </p>
            </div>
            <div className="p-6 rounded-xl border">
              <h3 className="text-xl font-semibold mb-2">Audit Trail</h3>
              <p className="text-muted-foreground">
                Immutable per-field transformation logs. Full before/after reports. Compliance-ready
                export formats.
              </p>
            </div>
            <div className="p-6 rounded-xl border">
              <h3 className="text-xl font-semibold mb-2">PII Protection</h3>
              <p className="text-muted-foreground">
                Patient IDs hashed before storage. AES-256 encryption at rest. RBAC with Admin/
                Analyst/Viewer roles.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-primary text-primary-foreground">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold tracking-tight mb-4">Ready to transform your patient data?</h2>
          <p className="text-primary-foreground/80 mb-8 max-w-2xl mx-auto">
            Start processing your first dataset in minutes. No external dependencies, no rate limits,
            complete data sovereignty.
          </p>
          <Link href="/upload">
            <Button size="lg" variant="secondary" className="gap-2">
              <Upload className="h-4 w-4" />
              Get Started Free
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 border-t">
        <div className="container mx-auto px-4 text-center text-muted-foreground text-sm">
          <p>GeoCare AI — India Patient Address Intelligence Platform</p>
          <p className="mt-1">Offline-first • Open-source only • Healthcare-grade</p>
        </div>
      </footer>
    </main>
  );
}