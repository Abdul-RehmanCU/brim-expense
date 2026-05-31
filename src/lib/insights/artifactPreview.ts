import Papa from 'papaparse'

export type InsightCsvPreview = {
  columns: string[]
  rows: string[][]
}

export type InsightDiagramNodePreview = {
  id: string
  title: string
  body: string
}

export type InsightDiagramPreview = {
  primaryNodes: InsightDiagramNodePreview[]
  filtersNode: InsightDiagramNodePreview | null
  citationsNode: InsightDiagramNodePreview | null
  rowNodes: InsightDiagramNodePreview[]
}

export type InsightBriefField = {
  label: string
  value: string
}

export type InsightBriefSection = {
  heading: string
  bullets: string[]
  paragraphs: string[]
  table: InsightCsvPreview | null
}

export type InsightBriefPreview = {
  title: string
  fields: InsightBriefField[]
  sections: InsightBriefSection[]
}

export function parseInsightCsvPreview(content: string): InsightCsvPreview | null {
  const trimmed = content.trim()
  if (!trimmed) {
    return null
  }

  const parsed = Papa.parse<string[]>(trimmed, {
    skipEmptyLines: true,
  })

  if (parsed.errors.length > 0 || parsed.data.length === 0) {
    return null
  }

  const [columns, ...rows] = parsed.data
  if (!columns || columns.length === 0) {
    return null
  }

  return {
    columns: columns.map((value) => value.trim()),
    rows: rows.map((row) => row.map((value) => value.trim())),
  }
}

export function parseInsightMermaidPreview(content: string): InsightDiagramPreview | null {
  const trimmed = content.trim()
  if (!trimmed) {
    return null
  }

  const nodeMap = new Map<string, InsightDiagramNodePreview>()

  for (const line of trimmed.split('\n').map((value) => value.trim())) {
    const nodeMatch = line.match(/^([A-Za-z0-9_]+)\["([\s\S]+)"\]$/)
    if (!nodeMatch) {
      continue
    }

    const [, id, rawLabel] = nodeMatch
    const parts = rawLabel.split('<br/>').map(decodeHtmlEntity)
    nodeMap.set(id, {
      id,
      title: parts[0] ?? id,
      body: parts.slice(1).join(' ').trim(),
    })
  }

  if (nodeMap.size === 0) {
    return null
  }

  const primaryNodes = ['question', 'validation', 'tool', 'intent', 'summary']
    .map((id) => nodeMap.get(id))
    .filter((node): node is InsightDiagramNodePreview => Boolean(node))

  const rowNodes = Array.from(nodeMap.values())
    .filter((node) => /^row\d+$/i.test(node.id))
    .sort((left, right) => extractRowIndex(left.id) - extractRowIndex(right.id))

  return {
    primaryNodes,
    filtersNode: nodeMap.get('filters') ?? null,
    citationsNode: nodeMap.get('citations') ?? null,
    rowNodes,
  }
}

export function parseInsightBriefPreview(content: string): InsightBriefPreview | null {
  const lines = content.split('\n')
  const titleLine = lines.find((line) => line.startsWith('# '))
  if (!titleLine) {
    return null
  }

  const fields: InsightBriefField[] = []
  const sections: InsightBriefSection[] = []
  let currentSection: { heading: string; lines: string[] } | null = null

  for (const line of lines.slice(1)) {
    if (line.startsWith('**') && !currentSection) {
      const fieldMatch = line.match(/^\*\*(.+?)\*\*: (.+)$/)
      if (fieldMatch) {
        fields.push({
          label: fieldMatch[1],
          value: fieldMatch[2],
        })
      }
      continue
    }

    if (line.startsWith('## ')) {
      if (currentSection) {
        sections.push(buildBriefSection(currentSection.heading, currentSection.lines))
      }
      currentSection = {
        heading: line.slice(3).trim(),
        lines: [],
      }
      continue
    }

    if (currentSection) {
      currentSection.lines.push(line)
    }
  }

  if (currentSection) {
    sections.push(buildBriefSection(currentSection.heading, currentSection.lines))
  }

  return {
    title: titleLine.slice(2).trim(),
    fields,
    sections,
  }
}

function buildBriefSection(heading: string, lines: string[]): InsightBriefSection {
  const bullets: string[] = []
  const paragraphs: string[] = []
  const tableLines: string[] = []

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      continue
    }

    if (line.startsWith('- ')) {
      bullets.push(line.slice(2).trim())
      continue
    }

    if (line.startsWith('|') && line.endsWith('|')) {
      tableLines.push(line)
      continue
    }

    paragraphs.push(line)
  }

  return {
    heading,
    bullets,
    paragraphs,
    table: parseMarkdownTable(tableLines),
  }
}

function parseMarkdownTable(lines: string[]): InsightCsvPreview | null {
  if (lines.length < 2) {
    return null
  }

  const [headerLine, separatorLine, ...rowLines] = lines
  if (!isMarkdownSeparatorRow(separatorLine)) {
    return null
  }

  const columns = splitMarkdownRow(headerLine)
  const rows = rowLines.map(splitMarkdownRow).filter((row) => row.length > 0)

  if (columns.length === 0) {
    return null
  }

  return {
    columns,
    rows,
  }
}

function splitMarkdownRow(line: string) {
  return line
    .slice(1, -1)
    .split('|')
    .map((cell) => cell.trim().replaceAll('\\|', '|'))
}

function isMarkdownSeparatorRow(line: string) {
  return /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|$/.test(line)
}

function extractRowIndex(value: string) {
  const match = value.match(/row(\d+)/i)
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER
}

function decodeHtmlEntity(value: string) {
  return value
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
}
