import {
  BookText,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  GitBranch,
  Loader2,
  Send,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { PolyAvatar } from '@/components/assistant/PolyAvatar'
import { PageScaffold } from '@/components/layout/PageScaffold'
import { ArtifactRenderPreview } from '@/components/talk-to-data/ArtifactRenderPreview'
import { SessionRail } from '@/components/talk-to-data/SessionRail'
import { TalkToDataResultTab } from '@/components/talk-to-data/TalkToDataResultTab'
import { Button } from '@/components/ui/button'
import {
  downloadInsightArtifactFile,
  generateInsightArtifactFile,
  type InsightCitation,
  type InsightQueryResponse,
} from '@/lib/api/backendClient'
import { useAssistant, useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import {
  buildInsightBriefMarkdown,
  buildInsightCsv,
  buildInsightMermaid,
  copyArtifactText,
  downloadBlobFile,
  type InsightArtifactTab,
} from '@/lib/insights/artifacts'
import { useUiPreferences } from '@/lib/ui/preferences'

type ResultWorkspaceTab = 'result' | 'artifacts'

export function TalkToDataPage() {
  const {
    question,
    setQuestion,
    session,
    sessions,
    conversation,
    selectedAssistantTurnId,
    selectedResult,
    isAsking,
    isLoadingSession,
    error,
    pageContext,
    setSelectedAssistantTurnId,
    askQuestion,
    selectSession,
    clearError,
    startNewSession,
  } = useAssistant()
  const [resultWorkspaceTab, setResultWorkspaceTab] = useState<ResultWorkspaceTab>('result')
  const [artifactTab, setArtifactTab] = useState<InsightArtifactTab>('diagram')
  const [artifactStatus, setArtifactStatus] = useState<string | null>(null)
  const { t } = useUiPreferences()

  const assistantContext = useMemo(
    () => ({
      routeId: 'talkToData' as const,
      title: 'Talk to Data',
      summary: 'You are in Poly\'s Ask workspace for finance questions, chart previews, result rows, and exports.',
      focus: selectedResult
        ? {
            type: 'insight_result',
            label: selectedResult.plan.intent,
            status: selectedResult.visualization ?? 'table',
          }
        : null,
      focusEntities: selectedResult
        ? [
            {
              type: 'insight_result',
              label: selectedResult.plan.intent,
              status: selectedResult.visualization ?? 'table',
              attributes: {
                tool: selectedResult.plan.tool,
                row_count: selectedResult.rows.length,
                citation_count: selectedResult.citations.length,
              },
            },
          ]
        : [],
      visibleEntities: selectedResult
        ? selectedResult.rows.slice(0, 10).map((row, index) => ({
            type: 'insight_row',
            id: `${selectedResult.plan.intent}-${index}`,
            label: row.label,
            status: typeof row.values.transaction_id === 'string' ? row.values.transaction_id : selectedResult.visualization ?? 'table',
            attributes: row.values,
          }))
        : [],
      artifacts: selectedResult
        ? [
            { type: 'diagram', label: 'Insight diagram', status: 'available' },
            { type: 'brief', label: 'Insight brief', status: 'available' },
            { type: 'csv', label: 'Insight CSV', status: 'available' },
          ]
        : [],
      metrics: selectedResult
        ? {
            row_count: selectedResult.rows.length,
            citation_count: selectedResult.citations.length,
          }
        : {},
      details: {
        quick_summary: selectedResult
          ? `The current selected answer is a ${selectedResult.visualization ?? 'table'} using ${selectedResult.plan.tool} with ${selectedResult.rows.length} row${selectedResult.rows.length === 1 ? '' : 's'}.`
          : 'Ask from the conversation panel and inspect the latest result, chart preview, and exports on the right.',
      },
      availableViews: ['conversation', 'result preview', 'artifacts'],
      suggestions: [],
    }),
    [selectedResult],
  )

  useAssistantPageContext(assistantContext)

  useEffect(() => {
    if (selectedAssistantTurnId) {
      setResultWorkspaceTab('result')
    }
  }, [selectedAssistantTurnId])

  return (
    <PageScaffold
      eyebrow={t('talkToData.eyebrow')}
      title={t('talkToData.title')}
      description="Ask finance questions over spend, policy, and risk data. The assistant now follows you across the app and uses page context when you ask from other workflows."
    >
      <section className="grid gap-5 xl:grid-cols-[280px_minmax(0,0.95fr)_minmax(360px,0.9fr)] 2xl:grid-cols-[300px_minmax(0,0.98fr)_minmax(420px,0.92fr)]">
        <SessionRail
          sessions={sessions}
          activeSessionId={session?.id ?? null}
          isLoading={isLoadingSession}
          onSelectSession={(sessionId) => {
            void selectSession(sessionId)
          }}
          onStartNewChat={startNewSession}
        />

        <section className="surface-panel flex min-h-[82vh] flex-col overflow-hidden">
          <div className="border-b border-border/70 px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <PolyAvatar className="size-12 rounded-2xl ring-2 ring-primary/15" />
                <div>
                  <p className="text-base font-semibold text-foreground">Talk with Poly</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Ask naturally, keep following up, and let Poly pull in the current app context when you need it.
                  </p>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="status-chip bg-muted text-muted-foreground">
                  {isLoadingSession ? 'Loading session' : session ? `Active ${session.id.slice(0, 8)}` : 'New session'}
                </span>
                {pageContext ? <span className="text-xs text-muted-foreground">Using {pageContext.title.toLowerCase()} context</span> : null}
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            {conversation.length > 0 ? (
              <div className="space-y-5">
                {conversation.map((turn) => (
                  <ConversationTurnCard
                    key={turn.id}
                    turn={turn}
                    isSelected={turn.id === selectedAssistantTurnId}
                    onSelect={() => {
                      if (turn.role === 'assistant' && turn.result) {
                        setSelectedAssistantTurnId(turn.id)
                        setResultWorkspaceTab('result')
                      }
                    }}
                  />
                ))}
              </div>
            ) : (
              <div className="grid gap-4">
                <div className="rounded-3xl border border-dashed border-border/70 bg-background/55 p-6">
                  <div className="flex items-start gap-3">
                    <PolyAvatar className="size-12 rounded-2xl ring-2 ring-primary/15" />
                    <div>
                      <p className="text-base font-semibold text-foreground">Chat first</p>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        Poly in the dock and this full workspace share the same session, so you can start anywhere and come here when the answer needs more room.
                      </p>
                    </div>
                  </div>
                </div>

              </div>
            )}
          </div>

          <form
            className="border-t border-border/70 px-6 py-5"
            onSubmit={(event) => {
              event.preventDefault()
              void askQuestion()
            }}
          >
            {error ? (
              <div className="mb-4 rounded-2xl border border-red-300/70 bg-red-100/70 p-4 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">
                <div className="flex items-start justify-between gap-3">
                  <span>{error}</span>
                  <button type="button" className="text-xs font-medium" onClick={clearError}>
                    Dismiss
                  </button>
                </div>
              </div>
            ) : null}

            <textarea
              className="min-h-36 w-full resize-y rounded-3xl border border-input bg-background px-5 py-4 text-base leading-7 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about spend, policy, or risk..."
            />
            <div className="mt-4 flex justify-end">
              <Button type="submit" disabled={isAsking || isLoadingSession || !question.trim()} size="lg">
                {isAsking ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Send className="size-4" aria-hidden="true" />}
                {isAsking ? 'Asking...' : 'Ask'}
              </Button>
            </div>
          </form>
        </section>

        <section className="surface-panel flex min-h-[82vh] min-h-0 flex-col overflow-hidden">
          <div className="border-b border-border/70 px-6 py-5">
            <div className="flex flex-col gap-4">
              <div className="flex items-start gap-4">
                <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <ShieldCheck className="size-5" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-base font-semibold text-foreground">Results</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {selectedResult
                      ? selectedResult.summary
                      : isAsking
                        ? 'Poly is building a fresh result preview for your latest question.'
                        : 'Pick an assistant response to inspect the rows, chart preview, citations, and exports.'}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2.5">
                {([
                  ['result', 'Result'],
                  ['artifacts', 'Artifacts'],
                ] as const).map(([tab, label]) => (
                  <button
                    key={tab}
                    type="button"
                    className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                      resultWorkspaceTab === tab
                        ? 'border-primary/60 bg-primary/10 text-foreground'
                        : 'border-border bg-muted text-muted-foreground hover:border-primary/40 hover:text-foreground'
                    }`}
                    onClick={() => setResultWorkspaceTab(tab)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {selectedResult ? (
              resultWorkspaceTab === 'result' ? (
                <TalkToDataResultTab result={selectedResult} />
              ) : (
                <InsightArtifacts
                  artifactStatus={artifactStatus}
                  artifactTab={artifactTab}
                  messageId={selectedAssistantTurnId}
                  onChangeArtifactTab={setArtifactTab}
                  onStatusChange={setArtifactStatus}
                  result={selectedResult}
                  sessionId={session?.id ?? selectedResult.session_id}
                />
              )
            ) : resultWorkspaceTab === 'result' ? (
              isAsking ? <LoadingResultState /> : <EmptyResultState />
            ) : (
              <EmptyArtifactState />
            )}
          </div>
        </section>
      </section>
    </PageScaffold>
  )
}

function LoadingResultState() {
  return (
    <div className="flex h-full min-h-[24rem] items-center justify-center px-6 py-10">
      <div className="max-w-md rounded-3xl border border-dashed border-border/70 bg-background/55 p-6 text-center">
        <p className="text-base font-semibold text-foreground">Refreshing result preview</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Poly is clearing the previous preview and rebuilding the latest chart, rows, and exports for this question.
        </p>
      </div>
    </div>
  )
}

function ConversationTurnCard({
  turn,
  isSelected,
  onSelect,
}: {
  turn: import('@/lib/assistant/types').AssistantConversationTurn
  isSelected: boolean
  onSelect: () => void
}) {
  const isAssistant = turn.role === 'assistant'
  const citations = turn.result?.citations ?? []

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-3xl border p-5 text-left transition ${
        isSelected ? 'border-primary/60 bg-primary/5' : 'border-border/70 bg-background hover:border-primary/40'
      } ${isAssistant ? 'cursor-pointer' : 'cursor-default'}`}
      disabled={!isAssistant || !turn.result}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{turn.role}</p>
          <p className="mt-2 text-sm leading-7 text-foreground">{turn.content}</p>
        </div>
        {turn.createdAt ? <span className="shrink-0 text-xs text-muted-foreground">{formatTimestamp(turn.createdAt)}</span> : null}
      </div>

      {isAssistant && turn.result ? (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap gap-2">
            <span className="status-chip bg-muted text-muted-foreground">Validated</span>
            <span className="status-chip bg-muted text-muted-foreground">{formatPlanValue(turn.result.visualization ?? 'table')}</span>
            <span className="status-chip bg-muted text-muted-foreground">{turn.result.rows.length} rows</span>
          </div>

          {citations.length > 0 ? (
            <div className="rounded-2xl bg-muted/55 p-4">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                <BookText className="size-3.5" aria-hidden="true" />
                Citations
              </div>
              <div className="mt-3 space-y-2">
                {citations.slice(0, 2).map((citation) => (
                  <CitationCard key={citation.clause_id ?? `${citation.rule_code}-${citation.text.slice(0, 24)}`} citation={citation} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </button>
  )
}

function InsightArtifacts({
  result,
  artifactTab,
  artifactStatus,
  messageId,
  onChangeArtifactTab,
  onStatusChange,
  sessionId,
}: {
  result: InsightQueryResponse
  artifactTab: InsightArtifactTab
  artifactStatus: string | null
  messageId: string | null
  onChangeArtifactTab: (tab: InsightArtifactTab) => void
  onStatusChange: (status: string | null) => void
  sessionId: string | null
}) {
  const artifacts = useMemo(
    () => ({
      csv: buildInsightCsv(result),
      diagram: buildInsightMermaid(result),
      brief: buildInsightBriefMarkdown(result),
    }),
    [result],
  )

  async function handleCopy(tab: InsightArtifactTab) {
    try {
      await copyArtifactText(artifacts[tab])
      onStatusChange(`${formatArtifactLabel(tab)} copied`)
    } catch {
      onStatusChange(`Could not copy ${formatArtifactLabel(tab).toLowerCase()}`)
    }
  }

  async function handleDownload(tab: InsightArtifactTab) {
    try {
      const persistedMessageId = messageId && !messageId.startsWith('assistant-') ? messageId : null
      const download = sessionId
        ? await downloadInsightArtifactFile({
            artifact: tab,
            sessionId,
            messageId: persistedMessageId,
          })
        : await generateInsightArtifactFile(tab, result)
      downloadBlobFile(download.blob, download.fileName)
      onStatusChange(`${formatArtifactLabel(tab)} downloaded`)
    } catch (downloadError) {
      onStatusChange(downloadError instanceof Error ? downloadError.message : `Could not download ${formatArtifactLabel(tab).toLowerCase()}`)
    }
  }

  return (
    <div className="space-y-5 p-6">
      <section className="rounded-3xl border border-border/70 bg-background/60 p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">Generated files</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">Preview the artifact instantly, then download a backend-generated file when you want to keep it.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => void handleDownload('csv')}>
              <FileSpreadsheet className="size-4" aria-hidden="true" />
              Download CSV
            </Button>
            <Button type="button" variant="outline" onClick={() => void handleDownload('diagram')}>
              <GitBranch className="size-4" aria-hidden="true" />
              Download Diagram
            </Button>
            <Button type="button" variant="outline" onClick={() => void handleDownload('brief')}>
              <FileText className="size-4" aria-hidden="true" />
              Download Brief
            </Button>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2.5">
          {(['diagram', 'brief', 'csv'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                artifactTab === tab
                  ? 'border-primary/60 bg-primary/10 text-foreground'
                  : 'border-border bg-muted text-muted-foreground hover:border-primary/40 hover:text-foreground'
              }`}
              onClick={() => onChangeArtifactTab(tab)}
            >
              {formatArtifactLabel(tab)}
            </button>
          ))}
          {artifactStatus ? <span className="status-chip bg-muted text-muted-foreground">{artifactStatus}</span> : null}
        </div>
      </section>

      <section className="rounded-3xl border border-border/70 bg-background/60 p-5">
        <div className="mb-4 flex items-center gap-2 text-base font-semibold text-foreground">
          <GitBranch className="size-4 text-primary" aria-hidden="true" />
          Rendered preview
        </div>
        <ArtifactRenderPreview artifactTab={artifactTab} artifactText={artifacts[artifactTab]} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_13rem]">
        <div className="subtle-panel overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-border/70 px-5 py-4">
            <p className="text-sm font-semibold text-foreground">{formatArtifactLabel(artifactTab)} source</p>
          </div>
          <pre className="max-h-[30rem] overflow-auto px-5 py-5 text-sm leading-7 text-muted-foreground whitespace-pre-wrap">{artifacts[artifactTab]}</pre>
        </div>

        <div className="subtle-panel flex flex-col gap-3 p-4">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Current artifact</p>
          <Button type="button" variant="outline" onClick={() => void handleCopy(artifactTab)}>
            <Copy className="size-4" aria-hidden="true" />
            Copy Preview
          </Button>
          <Button type="button" variant="outline" onClick={() => void handleDownload(artifactTab)}>
            <Download className="size-4" aria-hidden="true" />
            Download Preview
          </Button>
        </div>
      </div>
    </div>
  )
}

function CitationCard({ citation }: { citation: InsightCitation }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background p-4">
      <p className="text-sm font-medium text-foreground">{citation.title ?? citation.rule_code ?? 'Policy citation'}</p>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{citation.text}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        {citation.rule_code ? <span>Rule {citation.rule_code}</span> : null}
        {citation.source ? <span>Source {citation.source}</span> : null}
        {typeof citation.match_score === 'number' ? <span>Match {citation.match_score.toFixed(3)}</span> : null}
      </div>
    </div>
  )
}

function EmptyResultState() {
  return (
    <div className="grid gap-4 p-6">
      <div className="subtle-panel p-5 text-sm leading-6 text-muted-foreground">
        Results will show chart previews, rows, filters, and citations as soon as you select an assistant answer.
      </div>
      <div className="subtle-panel p-5 text-sm leading-6 text-muted-foreground">
        Use the conversation column to keep asking follow-ups without losing the current working set.
      </div>
    </div>
  )
}

function EmptyArtifactState() {
  return (
    <div className="grid gap-4 p-6">
      <div className="subtle-panel p-5 text-sm leading-6 text-muted-foreground">
        Artifacts appear here once you have a selected answer to export as a CSV, diagram, or briefing.
      </div>
      <div className="subtle-panel p-5 text-sm leading-6 text-muted-foreground">
        Keep the result above selected, then switch between diagram, brief, and CSV previews below.
      </div>
    </div>
  )
}

function formatPlanValue(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatArtifactLabel(value: InsightArtifactTab) {
  if (value === 'csv') {
    return 'CSV'
  }
  if (value === 'diagram') {
    return 'Diagram'
  }
  return 'Brief'
}

function formatTimestamp(value: string) {
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) {
    return value
  }

  return timestamp.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
