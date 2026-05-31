import type { InsightCitation, InsightQueryResponse, InsightResultRow } from '@/lib/api/backendClient'

export type InsightArtifactTab = 'csv' | 'diagram' | 'brief'

export function buildInsightCsv(result: InsightQueryResponse) {
  const columns = result.columns.length > 0 ? result.columns : inferColumns(result.rows)
  const rows = [
    columns.map(escapeCsvCell).join(','),
    ...result.rows.map((row) =>
      columns
        .map((column) => escapeCsvCell(formatCsvValue(column === 'label' ? row.label : row.values[column])))
        .join(','),
    ),
  ]
  return rows.join('\n')
}

export function buildInsightMermaid(result: InsightQueryResponse) {
  const filterSummary = formatFilters(result.plan.filters)
  const topRows = result.rows.slice(0, 5)
  const metric = pickPrimaryMetric(result)
  const lines = [
    'flowchart TD',
    `question["Question<br/>${escapeMermaid(result.question)}"]`,
    `validation["Validation<br/>${result.validation.valid ? 'Passed' : 'Blocked'}"]`,
    `tool["Tool<br/>${escapeMermaid(result.plan.tool)}"]`,
    `intent["Intent<br/>${escapeMermaid(result.plan.intent)}"]`,
    `summary["Answer<br/>${escapeMermaid(result.summary)}"]`,
    'question --> validation',
    'validation --> tool',
    'tool --> intent',
    'intent --> summary',
  ]

  if (filterSummary) {
    lines.push(`filters["Filters<br/>${escapeMermaid(filterSummary)}"]`)
    lines.push('tool --> filters')
    lines.push('filters --> summary')
  }

  if (topRows.length > 0) {
    for (const [index, row] of topRows.entries()) {
      const metricValue = row.values[metric]
      lines.push(
        `row${index}["${escapeMermaid(row.label)}<br/>${escapeMermaid(formatMetric(metric, metricValue))}"]`,
      )
      lines.push(`summary --> row${index}`)
    }
  }

  if (result.citations.length > 0) {
    lines.push(`citations["Policy citations<br/>${escapeMermaid(formatCitationCount(result.citations))}"]`)
    lines.push('summary --> citations')
  }

  return lines.join('\n')
}

export function buildInsightBriefMarkdown(result: InsightQueryResponse) {
  const lines: string[] = [
    `# ${result.plan.intent}`,
    '',
    `**Question**: ${result.question}`,
    '',
    `**Summary**: ${result.summary}`,
    '',
    '## Execution',
    '',
    `- Planner: ${result.planner_source}`,
    `- Tool: ${result.plan.tool}`,
    `- View: ${result.visualization ?? 'table'}`,
    `- Rows returned: ${result.metadata.returned_count ?? result.rows.length}`,
  ]

  const filterSummary = formatFilters(result.plan.filters)
  if (filterSummary) {
    lines.push(`- Filters: ${filterSummary}`)
  }

  if (result.rows.length > 0) {
    const columns = result.columns.length > 0 ? result.columns : inferColumns(result.rows)
    lines.push('', '## Result Preview', '')
    lines.push(`| ${columns.join(' | ')} |`)
    lines.push(`| ${columns.map(() => '---').join(' | ')} |`)
    for (const row of result.rows.slice(0, 12)) {
      lines.push(
        `| ${columns
          .map((column) => escapeMarkdownCell(formatCsvValue(column === 'label' ? row.label : row.values[column])))
          .join(' | ')} |`,
      )
    }
  }

  if (result.citations.length > 0) {
    lines.push('', '## Citations', '')
    for (const citation of result.citations) {
      lines.push(
        `- ${citation.title ?? citation.rule_code ?? 'Policy citation'}: ${citation.text}${
          citation.source ? ` (${citation.source})` : ''
        }`,
      )
    }
  }

  return lines.join('\n')
}

export function buildInsightArtifactFileName(result: InsightQueryResponse, artifact: InsightArtifactTab) {
  const baseName = slugify(result.plan.intent || result.plan.tool || result.question || 'insight')
  if (artifact === 'csv') {
    return `${baseName}.csv`
  }
  if (artifact === 'diagram') {
    return `${baseName}.mmd`
  }
  return `${baseName}.md`
}

export function downloadTextFile(content: string, fileName: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  downloadBlobFile(blob, fileName)
}

export function downloadBlobFile(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function copyArtifactText(content: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(content)
      return
    } catch {
      // Some embedded browsers expose the Clipboard API but still reject writes.
    }
  }

  const textArea = document.createElement('textarea')
  textArea.value = content
  textArea.style.position = 'fixed'
  textArea.style.opacity = '0'
  document.body.appendChild(textArea)
  textArea.focus()
  textArea.select()
  const copied = document.execCommand('copy')
  document.body.removeChild(textArea)
  if (!copied) {
    throw new Error('Copy failed')
  }
}

function pickPrimaryMetric(result: InsightQueryResponse) {
  return (
    result.columns.find((column) =>
      ['sum_amount_cad', 'policy_flag_count', 'risk_score', 'transaction_count', 'avg_amount_cad'].includes(column),
    ) ??
    Object.keys(result.rows[0]?.values ?? {})[0] ??
    'value'
  )
}

function inferColumns(rows: InsightResultRow[]) {
  const columns = ['label']
  for (const row of rows) {
    for (const key of Object.keys(row.values)) {
      if (!columns.includes(key)) {
        columns.push(key)
      }
    }
  }
  return columns
}

function formatFilters(filters: Record<string, unknown>) {
  const entries = Object.entries(filters)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : String(value)}`)
  return entries.join(' | ')
}

function formatCitationCount(citations: InsightCitation[]) {
  if (citations.length === 1) {
    return '1 citation'
  }
  return `${citations.length} citations`
}

function formatMetric(metric: string, value: unknown) {
  if (typeof value === 'number') {
    if (metric.includes('amount')) {
      return `CAD ${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  return String(value ?? '-')
}

function formatCsvValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (value === null || value === undefined) {
    return ''
  }
  return String(value)
}

function escapeCsvCell(value: string) {
  if (/[",\n]/.test(value)) {
    return `"${value.replaceAll('"', '""')}"`
  }
  return value
}

function escapeMarkdownCell(value: string) {
  return value.replaceAll('|', '\\|').replaceAll('\n', ' ')
}

function escapeMermaid(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('"', "'")
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('\n', ' ')
}

function slugify(value: string) {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return normalized || 'insight'
}
