import { ArrowDown, FileSpreadsheet, FileText } from 'lucide-react'
import { useMemo } from 'react'

import type { InsightArtifactTab } from '@/lib/insights/artifacts'
import {
  parseInsightBriefPreview,
  parseInsightCsvPreview,
  parseInsightMermaidPreview,
  type InsightBriefSection,
  type InsightCsvPreview,
  type InsightDiagramNodePreview,
} from '@/lib/insights/artifactPreview'

type ArtifactRenderPreviewProps = {
  artifactTab: InsightArtifactTab
  artifactText: string
}

export function ArtifactRenderPreview({
  artifactTab,
  artifactText,
}: ArtifactRenderPreviewProps) {
  if (artifactTab === 'csv') {
    return <CsvArtifactPreview csv={artifactText} />
  }

  if (artifactTab === 'brief') {
    return <BriefArtifactPreview content={artifactText} />
  }

  return <DiagramArtifactPreview content={artifactText} />
}

function CsvArtifactPreview({ csv }: { csv: string }) {
  const preview = useMemo(() => parseInsightCsvPreview(csv), [csv])

  if (!preview) {
    return <EmptyArtifactMessage message="No structured CSV rows are available for this answer yet." />
  }

  return (
    <div className="overflow-hidden rounded-3xl border border-border/70 bg-background/70">
      <div className="flex items-center gap-3 border-b border-border/70 px-5 py-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-primary">
          <FileSpreadsheet className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Structured preview</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {preview.rows.length.toLocaleString()} row{preview.rows.length === 1 ? '' : 's'} ready to export.
          </p>
        </div>
      </div>
      <PreviewTable preview={preview} />
    </div>
  )
}

function BriefArtifactPreview({ content }: { content: string }) {
  const preview = useMemo(() => parseInsightBriefPreview(content), [content])

  if (!preview) {
    return <EmptyArtifactMessage message="No formatted brief is available for this answer yet." />
  }

  return (
    <div className="grid gap-4">
      <section className="rounded-3xl border border-border/70 bg-background/70 p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-primary">
            <FileText className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Briefing</p>
            <p className="mt-2 text-base font-semibold text-foreground">{preview.title}</p>
          </div>
        </div>
        {preview.fields.length > 0 ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {preview.fields.map((field) => (
              <BriefFact key={field.label} label={field.label} value={field.value} />
            ))}
          </div>
        ) : null}
      </section>

      {preview.sections.map((section) => (
        <BriefSectionCard key={section.heading} section={section} />
      ))}
    </div>
  )
}

function DiagramArtifactPreview({ content }: { content: string }) {
  const preview = useMemo(() => parseInsightMermaidPreview(content), [content])

  if (!preview) {
    return <EmptyArtifactMessage message="No diagram nodes are available for this answer yet." />
  }

  return (
    <div className="grid gap-4">
      <section className="rounded-3xl border border-border/70 bg-background/70 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Flow</p>
        <div className="mt-4 grid gap-3">
          {preview.primaryNodes.map((node, index) => (
            <div key={node.id} className="space-y-3">
              <DiagramCard title={node.title} body={node.body} accent={node.id === 'summary'} />
              {index < preview.primaryNodes.length - 1 ? <DiagramArrow /> : null}
            </div>
          ))}
        </div>
      </section>

      {preview.filtersNode || preview.citationsNode ? (
        <section className="rounded-3xl border border-border/70 bg-background/70 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Context</p>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {preview.filtersNode ? <DiagramNodeCard node={preview.filtersNode} /> : null}
            {preview.citationsNode ? <DiagramNodeCard node={preview.citationsNode} /> : null}
          </div>
        </section>
      ) : null}

      {preview.rowNodes.length > 0 ? (
        <section className="rounded-3xl border border-border/70 bg-background/70 p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Top rows in the flow</p>
          <div className="mt-4 grid gap-3 xl:grid-cols-2">
            {preview.rowNodes.map((node) => (
              <DiagramNodeCard key={node.id} node={node} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

function DiagramCard({
  title,
  body,
  accent = false,
}: {
  title: string
  body: string
  accent?: boolean
}) {
  return (
    <div className={`rounded-2xl border p-4 ${accent ? 'border-primary/30 bg-primary/8' : 'border-border/70 bg-card/70'}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <p className="mt-2 text-sm leading-6 text-foreground">{body}</p>
    </div>
  )
}

function DiagramNodeCard({ node }: { node: InsightDiagramNodePreview }) {
  return <DiagramCard title={node.title} body={node.body || 'No details included in this node.'} />
}

function DiagramArrow() {
  return (
    <div className="flex justify-center">
      <ArrowDown className="size-4 text-muted-foreground" aria-hidden="true" />
    </div>
  )
}

function BriefSectionCard({ section }: { section: InsightBriefSection }) {
  return (
    <section className="rounded-3xl border border-border/70 bg-background/70 p-5">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{section.heading}</p>

      {section.paragraphs.length > 0 ? (
        <div className="mt-4 space-y-2">
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph} className="text-sm leading-7 text-muted-foreground">
              {paragraph}
            </p>
          ))}
        </div>
      ) : null}

      {section.bullets.length > 0 ? (
        <div className="mt-4 grid gap-3">
          {section.bullets.map((bullet) => (
            <div key={bullet} className="rounded-2xl border border-border/70 bg-card/70 p-4 text-sm leading-6 text-foreground">
              {bullet}
            </div>
          ))}
        </div>
      ) : null}

      {section.table ? (
        <div className="mt-4 overflow-hidden rounded-2xl border border-border/70">
          <PreviewTable preview={section.table} />
        </div>
      ) : null}
    </section>
  )
}

function BriefFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/70 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm text-foreground">{value}</p>
    </div>
  )
}

function PreviewTable({ preview }: { preview: InsightCsvPreview }) {
  return (
    <div className="max-h-[24rem] overflow-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="table-head">
          <tr>
            {preview.columns.map((column) => (
              <th key={column} className="px-4 py-3 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/70">
          {preview.rows.map((row, rowIndex) => (
            <tr key={`preview-row-${rowIndex}`} className="table-row">
              {preview.columns.map((column, columnIndex) => (
                <td key={`${column}-${rowIndex}-${columnIndex}`} className="px-4 py-3 align-top text-muted-foreground">
                  <span className="block max-w-[22rem] break-words leading-6">{row[columnIndex] || '-'}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EmptyArtifactMessage({ message }: { message: string }) {
  return (
    <div className="rounded-3xl border border-dashed border-border/70 bg-background/55 p-5 text-sm leading-6 text-muted-foreground">
      {message}
    </div>
  )
}
