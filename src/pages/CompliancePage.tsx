import { ShieldCheck, Sparkles, TrendingUp } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  getPolicyRepeatOffenders,
  getPolicySummary,
  listReviewQueueItems,
  refreshReviewQueue,
  scanPolicy,
  scanRisk,
  type PolicySeverity,
  type PolicyStatus,
  type PolicyScanSummary,
  type PolicyViolation,
  type RepeatOffenderSummary,
  type ReviewQueueItem,
  type RiskLevel,
  type RiskSignal,
} from '@/lib/api/backendClient'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { useUiPreferences } from '@/lib/ui/preferences'

const emptySummary: PolicyScanSummary = {
  total_scanned: 0,
  compliant: 0,
  excluded_non_expense: 0,
  evidence_required: 0,
  approval_evidence_required: 0,
  approval_evidence_needed: 0,
  context_needed: 0,
  policy_violations: 0,
  policy_violation: 0,
  review_required: 0,
  high_or_critical: 0,
  individual_flags: 0,
  violations_created: 0,
  duration_ms: 0,
  batch_count: 0,
}

const emptyRepeatOffenders: RepeatOffenderSummary = {
  employees: [],
  departments: [],
}

const reviewQueuePageSize = 25

const riskSeverityClass: Record<RiskLevel, string> = {
  low: 'bg-slate-100 text-slate-700 dark:bg-slate-400/10 dark:text-slate-100',
  medium: 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100',
  high: 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100',
  critical: 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100',
}

type ComplianceScanStageKey = 'policy' | 'risk' | 'queue' | 'finalizing'

type ReviewQueueGroup = {
  amountBreakdown: string
  category: string
  department: string | null
  employee: string | null
  highestPolicyStatus: PolicyStatus | null
  highestReviewLevel: PolicySeverity
  highestRiskLevel: RiskLevel
  items: ReviewQueueItem[]
  key: string
  merchant: string | null
  priority: number
  representative: ReviewQueueItem
  totalAmount: number
  transactionDate: string | null
}

export function CompliancePage() {
  const [summary, setSummary] = useState<PolicyScanSummary>(emptySummary)
  const [queueItems, setQueueItems] = useState<ReviewQueueItem[]>([])
  const [repeatOffenders, setRepeatOffenders] = useState<RepeatOffenderSummary>(emptyRepeatOffenders)
  const [severityFilter, setSeverityFilter] = useState<PolicySeverity | ''>('')
  const [statusFilter, setStatusFilter] = useState<PolicyStatus | ''>('')
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMoreQueueItems, setHasMoreQueueItems] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState(0)
  const [scanStage, setScanStage] = useState<ComplianceScanStageKey>('policy')
  const [error, setError] = useState<string | null>(null)
  const [expandedReviewGroups, setExpandedReviewGroups] = useState<Set<string>>(() => new Set())
  const { locale, t } = useUiPreferences()
  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: 'CAD',
      }),
    [locale],
  )

  const queueFilters = useMemo(
    () => ({
      review_level: severityFilter || undefined,
      policy_status: statusFilter || undefined,
      queue_status: 'open' as const,
      limit: reviewQueuePageSize,
    }),
    [severityFilter, statusFilter],
  )
  const reviewGroups = useMemo(() => groupReviewQueueItems(queueItems), [queueItems])
  const groupedTransactionCount = reviewGroups.reduce((count, group) => count + Math.max(0, group.items.length - 1), 0)
  const scanStages = useMemo(
    () => [
      {
        key: 'policy' as const,
        label: t('compliance.scanStagePolicy'),
        description: t('compliance.scanStagePolicyBody'),
        target: 26,
      },
      {
        key: 'risk' as const,
        label: t('compliance.scanStageRisk'),
        description: t('compliance.scanStageRiskBody'),
        target: 58,
      },
      {
        key: 'queue' as const,
        label: t('compliance.scanStageQueue'),
        description: t('compliance.scanStageQueueBody'),
        target: 84,
      },
      {
        key: 'finalizing' as const,
        label: t('compliance.scanStageFinalizing'),
        description: t('compliance.scanStageFinalizingBody'),
        target: 96,
      },
    ],
    [t],
  )
  const activeScanStage = scanStages.find((stage) => stage.key === scanStage) ?? scanStages[0]
  const assistantContext = useMemo(
    () => ({
      routeId: 'compliance' as const,
      title: 'Review',
      summary: `Reviewing ${queueItems.length} open queue item${queueItems.length === 1 ? '' : 's'} with ${summary.high_or_critical} high or critical cases.`,
      filters: {
        review_level: severityFilter || null,
        policy_status: statusFilter || null,
        queue_status: 'open',
      },
      details: {
        quick_summary: queueItems[0]?.reviewer_brief?.summary ?? composeReviewerContext(summary, queueItems),
        queue_overview: {
          total_scanned: summary.total_scanned,
          compliant: summary.compliant,
          review_required: summary.review_required,
          policy_violations: summary.policy_violation,
          excluded_non_expense: summary.excluded_non_expense,
          high_or_critical: summary.high_or_critical,
          open_queue_items: queueItems.length,
        },
        top_items: queueItems.slice(0, 3).map((item) => ({
          transaction_id: item.transaction_id,
          merchant: item.merchant ?? item.transaction_id,
          employee: item.employee ?? 'Assigned employee',
          department: item.department ?? 'Assigned department',
          amount_cad: item.amount_cad,
          review_level: item.review_level,
          policy_status: item.policy_status,
          risk_level: item.risk_level,
          next_action: item.next_action,
          reviewer_summary: item.reviewer_brief?.summary ?? item.ai_context ?? describeMergedQueueItem(item),
        })),
      },
      focus: queueItems[0]
        ? {
            type: 'review_queue_item',
            id: queueItems[0].id ?? queueItems[0].transaction_id,
            label: queueItems[0].merchant ?? queueItems[0].employee ?? queueItems[0].transaction_id,
            status: queueItems[0].policy_status,
          }
        : null,
      focusEntities: queueItems[0]
        ? [
            {
              type: 'review_queue_item',
              id: queueItems[0].id ?? queueItems[0].transaction_id,
              label: queueItems[0].merchant ?? queueItems[0].employee ?? queueItems[0].transaction_id,
              status: queueItems[0].policy_status,
              attributes: {
                amount_cad: queueItems[0].amount_cad,
                review_level: queueItems[0].review_level,
                risk_level: queueItems[0].risk_level,
              },
            },
          ]
        : [],
      visibleEntities: queueItems.slice(0, 8).map((item) => ({
        type: 'review_queue_item',
        id: item.id ?? item.transaction_id,
        label: item.merchant ?? item.employee ?? item.transaction_id,
        status: item.review_level,
        attributes: {
          amount_cad: item.amount_cad,
          policy_status: item.policy_status,
          risk_level: item.risk_level,
          next_action: item.next_action,
        },
      })),
      metrics: {
        total_scanned: summary.total_scanned,
        open_queue_items: queueItems.length,
        review_required: summary.review_required,
        policy_violations: summary.policy_violation,
        high_or_critical: summary.high_or_critical,
      },
      availableViews: ['review summary', 'open queue', 'repeat offenders'],
      suggestions: [
        'Why is the top review item flagged?',
        'Summarize the current review queue.',
      ],
    }),
    [queueItems, severityFilter, statusFilter, summary],
  )
  useAssistantPageContext(assistantContext)

  function toggleReviewGroup(groupKey: string) {
    setExpandedReviewGroups((currentGroups) => {
      const nextGroups = new Set(currentGroups)
      if (nextGroups.has(groupKey)) {
        nextGroups.delete(groupKey)
      } else {
        nextGroups.add(groupKey)
      }
      return nextGroups
    })
  }

  useEffect(() => {
    if (!isScanning) {
      return
    }

    const target = activeScanStage.target
    const timer = window.setInterval(() => {
      setScanProgress((current) => {
        if (current >= target) {
          return current
        }

        const remaining = target - current
        const increment = Math.max(1, Math.ceil(remaining / 5))
        return Math.min(target, current + increment)
      })
    }, 120)

    return () => {
      window.clearInterval(timer)
    }
  }, [activeScanStage.target, isScanning])

  async function loadMoreQueueItems() {
    setIsLoadingMore(true)
    setError(null)

    try {
      const loadedQueueItems = await listReviewQueueItems({
        ...queueFilters,
        offset: queueItems.length,
      })
      setQueueItems((currentItems) => sortQueueItems([...currentItems, ...loadedQueueItems]))
      setHasMoreQueueItems(loadedQueueItems.length === reviewQueuePageSize)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load more review items.')
    } finally {
      setIsLoadingMore(false)
    }
  }

  async function runPolicyScan() {
    setIsScanning(true)
    setScanStage('policy')
    setScanProgress(8)
    setError(null)

    try {
      const scanSummary = await scanPolicy({
        batch_size: 500,
        reset_existing: true,
        reset_synthetic_evidence: true,
      })
      setScanStage('risk')
      await scanRisk({ limit: 5000, reset_existing: true })
      setScanStage('queue')
      await refreshReviewQueue({ limit: 5000, reset_existing: true, persist: true })
      setScanStage('finalizing')
      const [loadedQueueItems, loadedRepeatOffenders] = await Promise.all([
        listReviewQueueItems(queueFilters),
        getPolicyRepeatOffenders(),
      ])
      setScanProgress(100)
      setSummary(scanSummary)
      setQueueItems(sortQueueItems(loadedQueueItems))
      setHasMoreQueueItems(loadedQueueItems.length === reviewQueuePageSize)
      setRepeatOffenders(loadedRepeatOffenders)
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : 'Could not complete layered review.')
    } finally {
      setIsScanning(false)
    }
  }

  useEffect(() => {
    let ignore = false

    async function loadInitialPolicyData() {
      try {
        const [loadedSummary, loadedQueueItems, loadedRepeatOffenders] = await Promise.all([
          getPolicySummary(),
          listReviewQueueItems(queueFilters),
          getPolicyRepeatOffenders(),
        ])

        if (!ignore) {
          setSummary(loadedSummary)
          setQueueItems(sortQueueItems(loadedQueueItems))
          setHasMoreQueueItems(loadedQueueItems.length === reviewQueuePageSize)
          setRepeatOffenders(loadedRepeatOffenders)
        }
      } catch (loadError) {
        if (!ignore) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load policy results.')
        }
      } finally {
        if (!ignore) {
          setIsLoading(false)
        }
      }
    }

    void loadInitialPolicyData()

    return () => {
      ignore = true
    }
  }, [queueFilters])

  return (
    <PageScaffold
      eyebrow={t('compliance.eyebrow')}
      title={t('compliance.title')}
      description={t('compliance.description')}
    >
      <section className="surface-panel p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ShieldCheck className="size-4" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold text-foreground">{t('compliance.checkIssuesTitle')}</p>
              <p className="mt-1 text-sm text-muted-foreground">{t('compliance.checkIssuesBody')}</p>
            </div>
          </div>
          <Button type="button" onClick={runPolicyScan} disabled={isScanning}>
            {isScanning ? t('actions.scanning') : t('compliance.checkTransactions')}
          </Button>
        </div>

        {isScanning ? <ComplianceScanProgress activeStage={activeScanStage} progress={scanProgress} stages={scanStages} /> : null}

        {error ? <p className="mt-3 rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">{error}</p> : null}

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SummaryMetric label={t('compliance.scanned')} value={summary.total_scanned} locale={locale} />
          <SummaryMetric label={t('compliance.compliant')} value={summary.compliant} locale={locale} />
          <SummaryMetric label={t('compliance.approvalEvidenceNeeded')} value={summary.approval_evidence_needed} locale={locale} />
          <SummaryMetric label={t('compliance.needContext')} value={summary.context_needed} locale={locale} />
          <SummaryMetric label={t('compliance.reviewRequired')} value={summary.review_required} locale={locale} />
          <SummaryMetric label={t('compliance.policyViolations')} value={summary.policy_violation} locale={locale} />
          <SummaryMetric label={t('compliance.excludedNonExpense')} value={summary.excluded_non_expense} locale={locale} />
          <SummaryMetric label={t('compliance.highCritical')} value={summary.high_or_critical} locale={locale} />
          <SummaryMetric label={t('compliance.individualFlags')} value={summary.individual_flags || summary.violations_created} locale={locale} />
        </div>

        {summary.duration_ms > 0 || summary.batch_count > 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            {t('compliance.lastScanSummary')
              .replace('{duration}', formatDuration(summary.duration_ms))
              .replace('{batches}', summary.batch_count.toLocaleString(locale))}
          </p>
        ) : null}

        <p className="mt-4 rounded-lg border border-amber-300/60 bg-amber-100/60 p-3 text-sm text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
          {t('compliance.evidenceNote')}
        </p>
      </section>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)]">
        <TopFindingsPanel currencyFormatter={currencyFormatter} groups={reviewGroups} items={queueItems} locale={locale} summary={summary} />
        <div className="grid gap-3">
          <RepeatOffenderPanel title={t('compliance.employeesWithOpenFlags')} items={repeatOffenders.employees} locale={locale} />
          <RepeatOffenderPanel title={t('compliance.departmentsWithOpenFlags')} items={repeatOffenders.departments} locale={locale} />
        </div>
      </section>

      <section className="surface-panel overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border/70 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">{t('compliance.reviewItemsTitle')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('compliance.reviewItemsBody')}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              className="h-8 rounded-lg border border-input bg-background px-2 text-sm text-foreground"
              value={severityFilter}
              onChange={(event) => setSeverityFilter(event.target.value as PolicySeverity | '')}
              aria-label={t('compliance.filterBySeverity')}
            >
              <option value="">{t('compliance.allSeverities')}</option>
              <option value="critical">{t('compliance.critical')}</option>
              <option value="high">{t('compliance.high')}</option>
              <option value="medium">{t('compliance.medium')}</option>
              <option value="low">{t('compliance.low')}</option>
            </select>
            <select
              className="h-8 rounded-lg border border-input bg-background px-2 text-sm text-foreground"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as PolicyStatus | '')}
              aria-label={t('compliance.filterByPolicyStatus')}
            >
              <option value="">{t('compliance.allStatuses')}</option>
              <option value="policy_violation">{t('compliance.policyViolation')}</option>
              <option value="approval_evidence_needed">{t('compliance.approvalEvidenceNeeded')}</option>
              <option value="context_needed">{t('compliance.contextNeeded')}</option>
              <option value="review_required">{t('compliance.reviewRequired')}</option>
              <option value="excluded_non_expense">{t('compliance.excludedNonExpense')}</option>
            </select>
          </div>
        </div>

        {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('compliance.loading')}</p> : null}

        {!isLoading && queueItems.length === 0 ? <p className="p-4 text-sm text-muted-foreground">{t('compliance.noMatches')}</p> : null}

        {queueItems.length > 0 ? (
          <>
            <div className="desktop-scroll max-h-[44rem] space-y-3 overflow-y-auto p-4">
              {groupedTransactionCount > 0 ? (
                <p className="rounded-xl border border-blue-300/60 bg-blue-100/60 p-3 text-sm text-blue-900 dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-100">
                  Grouped {groupedTransactionCount.toLocaleString(locale)} repeated or related transactions into{' '}
                  {reviewGroups.filter((group) => group.items.length > 1).length.toLocaleString(locale)} expandable review cluster
                  {reviewGroups.filter((group) => group.items.length > 1).length === 1 ? '' : 's'}.
                </p>
              ) : null}
              {reviewGroups.map((group) => (
                <ReviewQueueGroupCard
                  key={group.key}
                  currencyFormatter={currencyFormatter}
                  group={group}
                  isExpanded={expandedReviewGroups.has(group.key)}
                  locale={locale}
                  onToggle={() => toggleReviewGroup(group.key)}
                />
              ))}
            </div>
            {hasMoreQueueItems ? (
              <div className="border-t border-border/70 p-4">
                <Button type="button" variant="outline" onClick={() => void loadMoreQueueItems()} disabled={isLoadingMore}>
                  {isLoadingMore ? 'Loading more...' : 'Load more review items'}
                </Button>
              </div>
            ) : null}
          </>
        ) : null}
      </section>
    </PageScaffold>
  )
}

function ComplianceScanProgress({
  activeStage,
  progress,
  stages,
}: {
  activeStage: {
    description: string
    key: ComplianceScanStageKey
    label: string
    target: number
  }
  progress: number
  stages: Array<{
    description: string
    key: ComplianceScanStageKey
    label: string
    target: number
  }>
}) {
  const { t } = useUiPreferences()
  const activeIndex = stages.findIndex((stage) => stage.key === activeStage.key)

  return (
    <div className="mt-4 rounded-xl border border-sky-300/50 bg-sky-100/50 p-3 dark:border-sky-400/20 dark:bg-sky-400/10">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">{t('compliance.mlProgressTitle')}</p>
          <p className="mt-1 text-sm text-muted-foreground">{activeStage.description}</p>
        </div>
        <p className="text-sm font-semibold tabular-nums text-sky-700 dark:text-sky-100">{Math.round(progress)}%</p>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-sky-200/80 dark:bg-sky-950/60">
        <div
          className="h-full rounded-full bg-sky-600 transition-[width] duration-300 ease-out dark:bg-sky-300"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {stages.map((stage, index) => {
          const isComplete = index < activeIndex
          const isActive = index === activeIndex

          return (
            <div
              key={stage.key}
              className={`rounded-lg border p-2 transition-colors ${
                isActive
                  ? 'border-sky-400/70 bg-background/90'
                  : isComplete
                    ? 'border-emerald-300/70 bg-emerald-100/50 dark:border-emerald-400/20 dark:bg-emerald-400/10'
                    : 'border-border/70 bg-background/60'
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`flex size-5 items-center justify-center rounded-full text-[11px] font-semibold ${
                    isActive
                      ? 'bg-sky-600 text-white dark:bg-sky-300 dark:text-slate-950'
                      : isComplete
                        ? 'bg-emerald-600 text-white dark:bg-emerald-300 dark:text-slate-950'
                        : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {index + 1}
                </span>
                <p className="text-sm font-medium text-foreground">{stage.label}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SummaryMetric({ label, locale, value }: { label: string; locale: string; value: number }) {
  return (
    <div className="subtle-panel p-3">
      <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value.toLocaleString(locale)}</p>
    </div>
  )
}

function TopFindingsPanel({
  currencyFormatter,
  groups,
  items,
  locale,
  summary,
}: {
  currencyFormatter: Intl.NumberFormat
  groups: ReviewQueueGroup[]
  items: ReviewQueueItem[]
  locale: string
  summary: PolicyScanSummary
}) {
  const { t } = useUiPreferences()
  const topGroups = groups.slice(0, 3)
  const visibleHighCritical = items.filter((item) => item.review_level === 'high' || item.review_level === 'critical').length
  const visibleSignals = items.reduce((total, item) => total + policyFlagsFor(item).length + riskSignalsFor(item).length, 0)
  const reviewRequiredCount = summary.total_scanned > 0 ? summary.review_required : items.length
  const highCriticalCount = summary.total_scanned > 0 ? summary.high_or_critical : visibleHighCritical
  const totalSignals = summary.total_scanned > 0 ? (summary.individual_flags || summary.violations_created) : visibleSignals
  const topGroup = topGroups[0]

  return (
    <section className="surface-panel overflow-hidden">
      <div className="border-b border-border/70 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-200">
              <TrendingUp className="size-4" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold text-foreground">{t('compliance.attentionTitle')}</p>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('compliance.attentionBody')}</p>
            </div>
          </div>
          <div className="rounded-xl border border-border/70 bg-muted/35 p-3 text-sm text-muted-foreground xl:max-w-sm">
            <div className="flex items-center gap-2 font-semibold text-foreground">
              <Sparkles className="size-4" aria-hidden="true" />
              {t('compliance.quickSummary')}
            </div>
            <p className="mt-1 leading-5">
              {topGroup ? describeReviewGroupSummary(topGroup, currencyFormatter) : composeReviewerContext(summary, items)}
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <SummaryMetric label={t('compliance.reviewRequired')} value={reviewRequiredCount} locale={locale} />
          <SummaryMetric label={t('compliance.highCritical')} value={highCriticalCount} locale={locale} />
          <SummaryMetric label="Signals" value={totalSignals} locale={locale} />
        </div>
      </div>

      {topGroups.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">{t('compliance.combinedFindingsEmpty')}</p>
      ) : (
        <div className="grid gap-3 p-4 lg:grid-cols-3">
          {topGroups.map((group) => (
            <article key={group.key} className="rounded-xl border border-border/70 bg-background/70 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{group.merchant ?? 'Unknown merchant'}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {group.employee ?? 'Synthetic Employee'} · {group.department ?? 'Synthetic Department'}
                  </p>
                </div>
                <span className={`status-chip ${riskSeverityClass[group.highestReviewLevel]}`}>
                  {formatSignalLabel(group.highestReviewLevel)} review
                </span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {group.items.length > 1 ? (
                  <span className="status-chip bg-blue-600 text-white dark:bg-blue-300 dark:text-slate-950">
                    {group.items.length.toLocaleString(locale)} related
                  </span>
                ) : null}
                <StatusPill value={group.highestPolicyStatus ?? 'compliant'} />
                <span className={`status-chip ${riskSeverityClass[group.highestRiskLevel]}`}>{formatSignalLabel(group.highestRiskLevel)} risk</span>
                <span className="ml-auto text-sm font-semibold tabular-nums text-foreground">{currencyFormatter.format(group.totalAmount)}</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{describeReviewGroup(group)}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function ReviewQueueGroupCard({
  currencyFormatter,
  group,
  isExpanded,
  locale,
  onToggle,
}: {
  currencyFormatter: Intl.NumberFormat
  group: ReviewQueueGroup
  isExpanded: boolean
  locale: string
  onToggle: () => void
}) {
  const { t } = useUiPreferences()

  if (group.items.length === 1) {
    return <ReviewQueueCard currencyFormatter={currencyFormatter} item={group.representative} />
  }

  const flagSummaries = getGroupFlagSummaries(group)
  const exactDuplicateCount = getExactDuplicateCount(group.items)

  return (
    <article className="rounded-2xl border border-blue-300/70 bg-blue-50/70 p-4 shadow-sm dark:border-blue-400/25 dark:bg-blue-400/10">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-foreground">{group.merchant ?? '-'}</p>
            <span className="status-chip bg-blue-600 text-white dark:bg-blue-300 dark:text-slate-950">
              {group.items.length.toLocaleString(locale)} related transactions
            </span>
            <StatusPill value={group.highestPolicyStatus ?? 'compliant'} />
            <span className={`status-chip ${riskSeverityClass[group.highestRiskLevel]}`}>{formatSignalLabel(group.highestRiskLevel)} risk</span>
            <span className="status-chip bg-muted text-muted-foreground">Priority {group.priority}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>{group.employee ?? 'Assigned employee'}</span>
            <span>{group.department ?? 'Assigned department'}</span>
            <span>{group.transactionDate ?? '-'}</span>
            <span>{group.category}</span>
          </div>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-muted-foreground">
            Same reviewer context detected: {group.items.length.toLocaleString(locale)} rows share the same employee, merchant, date, and category.
            Review them together to decide whether this is a duplicate, recurring fee, cash/ATM pattern, or valid related activity.
          </p>
        </div>

        <div className="shrink-0 text-left xl:text-right">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Cluster total</p>
          <p className="text-2xl font-semibold tabular-nums text-foreground">{currencyFormatter.format(group.totalAmount)}</p>
          <p className="mt-1 text-xs text-muted-foreground">{group.amountBreakdown}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <section className="subtle-panel p-3">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Pattern</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {exactDuplicateCount > 0
              ? `${exactDuplicateCount.toLocaleString(locale)} exact duplicate pair${exactDuplicateCount === 1 ? '' : 's'} found inside this cluster.`
              : 'No exact duplicate pair inside this cluster, but the rows share enough context to review together.'}
          </p>
        </section>
        <section className="subtle-panel p-3">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.details')}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {flagSummaries.slice(0, 4).map((flag) => (
              <span key={flag.key} className={`status-chip ${flag.className}`}>
                {flag.label}
              </span>
            ))}
            {flagSummaries.length > 4 ? (
              <span className="status-chip bg-muted text-muted-foreground">+{flagSummaries.length - 4} more</span>
            ) : null}
          </div>
        </section>
        <section className="subtle-panel p-3">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.nextAction')}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Review the cluster once, then expand only if you need row-level evidence, citations, or transaction IDs.
          </p>
        </section>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-blue-200/80 pt-4 dark:border-blue-300/20">
        <p className="text-xs leading-5 text-muted-foreground">
          Amounts: {group.items.map((item) => currencyFormatter.format(item.amount_cad)).join(', ')}
        </p>
        <Button type="button" variant="outline" onClick={onToggle} aria-expanded={isExpanded}>
          {isExpanded ? 'Hide individual rows' : 'Expand individual rows'}
        </Button>
      </div>

      {isExpanded ? (
        <div className="mt-4 space-y-3">
          {group.items.map((item) => (
            <ReviewQueueCard key={item.transaction_id} currencyFormatter={currencyFormatter} item={item} />
          ))}
        </div>
      ) : null}
    </article>
  )
}

function ReviewQueueCard({
  currencyFormatter,
  item,
}: {
  currencyFormatter: Intl.NumberFormat
  item: ReviewQueueItem
}) {
  const { t } = useUiPreferences()

  return (
    <article className="rounded-2xl border border-border/70 bg-background/72 p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-foreground">{item.merchant ?? '-'}</p>
            <StatusPill value={item.policy_status ?? 'compliant'} />
            <span className={`status-chip ${riskSeverityClass[item.risk_level ?? 'low']}`}>{formatSignalLabel(item.risk_level ?? 'low')} risk</span>
            <span className="status-chip bg-muted text-muted-foreground">Priority {item.review_priority}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span>{item.employee ?? 'Assigned employee'}</span>
            <span>{item.department ?? 'Assigned department'}</span>
            <span>{item.transaction_date ?? '-'}</span>
            <span>{item.category}</span>
          </div>
        </div>

        <div className="shrink-0 text-left xl:text-right">
          <p className="text-xl font-semibold tabular-nums text-foreground">{currencyFormatter.format(item.amount_cad)}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <section className="subtle-panel p-3">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.flaggedReason')}</p>
          <div className="mt-2">
            <PolicyStatusCell item={item} />
          </div>
          <div className="mt-3">
            <RiskStatusCell item={item} />
          </div>
        </section>

        <section className="subtle-panel p-3">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.details')}</p>
          <div className="mt-2">
            <ReviewQueueDetails item={item} />
          </div>
        </section>

        <section className="subtle-panel p-3">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.nextAction')}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.next_action}</p>
          <div className="mt-3 border-t border-border/70 pt-3">
            <ReviewerBriefCell item={item} />
          </div>
        </section>
      </div>
    </article>
  )
}

function RepeatOffenderPanel({
  items,
  locale,
  title,
}: {
  items: RepeatOffenderSummary['employees']
  locale: string
  title: string
}) {
  const { t } = useUiPreferences()

  return (
    <section className="surface-panel p-4">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {items.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">{t('compliance.noOpenPolicyFlags')}</p> : null}
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div key={item.id ?? item.name} className="flex items-center justify-between gap-3 rounded-lg bg-muted px-3 py-2">
            <span className="truncate text-sm text-muted-foreground">{item.name}</span>
            <span className="status-chip bg-background text-foreground">{item.open_violations.toLocaleString(locale)}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function ReviewQueueDetails({ item }: { item: ReviewQueueItem }) {
  const { t } = useUiPreferences()
  const flags = getMergedFlagSummaries(item)

  return (
    <details className="group">
      <summary className="list-none cursor-pointer text-sm marker:hidden [&::-webkit-details-marker]:hidden">
        <span className="font-medium text-foreground">{t('compliance.viewFlagDetails').replace('{count}', String(flags.length))}</span>
        <span className="mt-1 flex flex-wrap gap-1.5">
          {flags.slice(0, 2).map((flag) => (
            <span key={flag.key} className={`status-chip ${flag.className}`}>
              {flag.label}
            </span>
          ))}
          {flags.length > 2 ? (
            <span className="status-chip bg-muted text-muted-foreground">
              {t('compliance.moreFlags').replace('{count}', String(flags.length - 2))}
            </span>
          ) : null}
        </span>
      </summary>
      <div className="mt-3 hidden space-y-2 rounded-xl border border-border/70 bg-card/70 p-3 group-open:block">
        {policyFlagsFor(item).map((violation) => (
          <div key={`${item.transaction_id}-${violation.rule_code}`} className="rounded-lg border border-border/70 bg-background/70 p-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-foreground">{formatPolicyRuleLabel(violation.rule_code)}</span>
              <SeverityPill value={violation.severity} />
            </div>
            <p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">{violation.rule_code}</p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{violation.explanation}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{violation.required_action}</p>
          </div>
        ))}
        {riskSignalsFor(item).map((signal) => (
          <div key={`${item.transaction_id}-${signal.type}`} className="rounded-lg border border-border/70 bg-background/70 p-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="break-all font-mono text-xs text-muted-foreground">{formatSignalLabel(signal.type)}</span>
              <span className={`status-chip ${riskSeverityClass[signal.severity]}`}>{formatSignalLabel(signal.severity)}</span>
            </div>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{signal.message}</p>
          </div>
        ))}
      </div>
    </details>
  )
}

function ReviewerBriefCell({ item }: { item: ReviewQueueItem }) {
  const { t } = useUiPreferences()
  const brief = item.reviewer_brief

  if (!brief) {
    return <span>{item.ai_context ?? '-'}</span>
  }

  const confidenceClass =
    brief.confidence === 'high'
      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-100'
      : brief.confidence === 'medium'
        ? 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'
        : 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'

  return (
    <details className="group">
      <summary className="list-none cursor-pointer text-sm marker:hidden [&::-webkit-details-marker]:hidden">
        <span className="block leading-6 text-muted-foreground">{brief.summary}</span>
        <span className="mt-2 flex flex-wrap gap-1.5">
          <span className={`status-chip ${confidenceClass}`}>{formatSignalLabel(brief.confidence)} confidence</span>
          <span className="status-chip bg-muted text-muted-foreground">
            {brief.cited_policy_clauses.length > 0 ? `${brief.cited_policy_clauses.length} ${t('talkToData.citations').toLowerCase()}` : t('compliance.noCitations')}
          </span>
        </span>
      </summary>
      <div className="mt-3 hidden space-y-3 rounded-xl border border-border/70 bg-card/70 p-3 group-open:block">
        <p className="text-xs leading-5 text-muted-foreground">{brief.advisory_notice}</p>

        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.groundedReasons')}</p>
          <ul className="mt-2 space-y-1.5">
            {brief.key_reasons.map((reason) => (
              <li key={reason} className="text-sm leading-5 text-muted-foreground">
                {reason}
              </li>
            ))}
          </ul>
        </div>

        {brief.missing_context.length > 0 ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.contextNeeded')}</p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{brief.missing_context.join(', ')}</p>
          </div>
        ) : null}

        {brief.cited_policy_clauses.length > 0 ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.policyCitations')}</p>
            <div className="mt-2 space-y-2">
              {brief.cited_policy_clauses.slice(0, 2).map((clause) => (
                <div key={clause.clause_id ?? `${clause.rule_code}-${clause.text.slice(0, 32)}`} className="rounded-lg bg-muted p-2">
                  <p className="text-xs font-medium text-foreground">{clause.title ?? clause.rule_code ?? t('compliance.policyClause')}</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{clause.text}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{t('compliance.groundingWarnings')}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{brief.grounding_warnings.join(' ')}</p>
        </div>
      </div>
    </details>
  )
}

function PolicyStatusCell({ item }: { item: ReviewQueueItem }) {
  const policyStatus = item.policy_status ?? 'compliant'

  return (
    <div className="space-y-1.5">
      <StatusPill value={policyStatus} />
      <p className="text-xs leading-5 text-muted-foreground">{getPolicyStatusDescription(policyStatus, policyFlagsFor(item))}</p>
    </div>
  )
}

function RiskStatusCell({ item }: { item: ReviewQueueItem }) {
  const riskLevel = item.risk_level ?? 'low'

  return (
    <div className="space-y-1.5">
      <span className={`status-chip ${riskSeverityClass[riskLevel]}`}>{formatSignalLabel(riskLevel)} risk</span>
      <p className="text-xs leading-5 text-muted-foreground">{getRiskStatusDescription(riskLevel, riskSignalsFor(item), item.risk_score)}</p>
    </div>
  )
}

function StatusPill({ value }: { value: string }) {
  const { t } = useUiPreferences()

  return <span className="status-chip bg-muted text-muted-foreground">{formatLabel(value, t)}</span>
}

function SeverityPill({ value }: { value: string }) {
  const { t } = useUiPreferences()
  const className =
    value === 'critical'
      ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
      : value === 'high'
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
        : value === 'medium'
          ? 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'
          : 'bg-muted text-muted-foreground'

  return <span className={`status-chip ${className}`}>{formatLabel(value, t)}</span>
}

function formatLabel(value: string, t: ReturnType<typeof useUiPreferences>['t']) {
  const labelByValue: Record<string, string> = {
    approval_evidence_needed: t('compliance.approvalEvidenceNeeded'),
    compliant: t('compliance.compliant'),
    context_needed: t('compliance.contextNeeded'),
    critical: t('compliance.critical'),
    excluded_non_expense: t('compliance.excludedNonExpense'),
    high: t('compliance.high'),
    low: t('compliance.low'),
    medium: t('compliance.medium'),
    policy_violation: t('compliance.policyViolation'),
    review_required: t('compliance.reviewRequired'),
  }

  return labelByValue[value] ?? value.replaceAll('_', ' ')
}

function formatSignalLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function composeReviewerContext(summary: PolicyScanSummary, queueItems: ReviewQueueItem[]) {
  if (summary.total_scanned === 0 && queueItems.length === 0) {
    return 'Run the layered scan to combine policy compliance, anomaly detection, and reviewer guidance.'
  }

  const highRisk = queueItems.filter((item) => item.risk_level === 'high' || item.risk_level === 'critical').length
  const splitSignals = queueItems.filter((item) => riskSignalsFor(item).some((signal) => signal.type === 'split_transaction_pattern')).length
  const duplicateSignals = queueItems.filter((item) => riskSignalsFor(item).some((signal) => signal.type === 'duplicate_charge')).length
  const mlSignals = queueItems.filter((item) => riskSignalsFor(item).some((signal) => signal.type === 'ml_isolation_forest_outlier')).length
  const topMerchant = queueItems[0]?.merchant ?? 'the highest-ranked transaction'

  return [
    `${summary.approval_evidence_needed.toLocaleString()} transactions need approval evidence and ${summary.review_required.toLocaleString()} need review after policy scanning.`,
    `${queueItems.length.toLocaleString()} merged review queue items are visible for approval triage.`,
    highRisk > 0
                      ? `${highRisk.toLocaleString()} visible risk records are high or critical; start with ${topMerchant}.`
                      : 'No high or critical risk records are visible at the selected threshold.',
    splitSignals || duplicateSignals || mlSignals
      ? `Risk signals include ${duplicateSignals.toLocaleString()} possible duplicate records, ${splitSignals.toLocaleString()} split-threshold patterns, and ${mlSignals.toLocaleString()} transactions flagged as unusual based on amount, merchant, category, timing, or employee baseline patterns.`
      : 'No duplicate, split-threshold, or unusual-pattern signals are visible at the selected threshold.',
  ].join(' ')
}

function describeMergedQueueItem(item: ReviewQueueItem) {
  const policyStatus = item.policy_status ?? 'compliant'
  const riskLevel = item.risk_level ?? 'low'
  const firstPolicyFlag = policyFlagsFor(item)[0]
  const firstRiskSignal = riskSignalsFor(item)[0]

  if (firstPolicyFlag && firstRiskSignal) {
    return `${formatSignalLabel(policyStatus)}: ${firstPolicyFlag.explanation} Risk detection adds ${formatSignalLabel(firstRiskSignal.type).toLowerCase()}: ${firstRiskSignal.message}`
  }

  if (firstPolicyFlag) {
    return `${formatSignalLabel(policyStatus)}: ${firstPolicyFlag.explanation}`
  }

  if (firstRiskSignal) {
    return `${formatSignalLabel(riskLevel)} risk: ${firstRiskSignal.message}`
  }

  return `${formatSignalLabel(policyStatus)} with ${formatSignalLabel(riskLevel).toLowerCase()} risk. Review the row for context and next action.`
}

function describeReviewGroup(group: ReviewQueueGroup) {
  if (group.items.length === 1) {
    return describeMergedQueueItem(group.representative)
  }

  const exactDuplicateCount = getExactDuplicateCount(group.items)
  const duplicateContext =
    exactDuplicateCount > 0
      ? `${exactDuplicateCount} exact duplicate pair${exactDuplicateCount === 1 ? '' : 's'} appear inside the group.`
      : 'The rows are not exact duplicates, but share reviewer context.'

  return `${formatSignalLabel(group.highestRiskLevel)} risk cluster: ${group.items.length} same-day ${group.category.toLowerCase()} rows for the same employee and merchant. ${duplicateContext}`
}

function describeReviewGroupSummary(group: ReviewQueueGroup, currencyFormatter: Intl.NumberFormat) {
  if (group.items.length === 1) {
    return group.representative.reviewer_brief?.summary ?? describeMergedQueueItem(group.representative)
  }

  return `${group.merchant ?? 'Top merchant'} is grouped into ${group.items.length} related review transactions totaling ${currencyFormatter.format(
    group.totalAmount,
  )}. Review the cluster once, then expand only when row-level evidence is needed.`
}

function getPolicyStatusDescription(status: string, flags: PolicyViolation[]) {
  const firstFlag = flags[0]

  if (firstFlag) {
    return `${formatPolicyRuleLabel(firstFlag.rule_code)}: ${firstFlag.required_action}`
  }

  const descriptionByStatus: Record<string, string> = {
    approval_evidence_needed: 'Approval or receipt evidence should be collected before reimbursement proceeds.',
    compliant: 'No open policy finding is attached to this queue row.',
    context_needed: 'Finance needs more business context before deciding the expense.',
    excluded_non_expense: 'Transaction appears outside normal reimbursable expense review.',
    policy_violation: 'Policy rule indicates this should not proceed without finance review.',
    review_required: 'A reviewer should inspect the transaction before approval.',
  }

  return descriptionByStatus[status] ?? 'Policy output from the backend review queue.'
}

function getRiskStatusDescription(level: RiskLevel, signals: RiskSignal[], score: number) {
  const firstSignal = signals[0]

  if (firstSignal) {
    return `${formatSignalLabel(firstSignal.type)}: ${firstSignal.message}`
  }

  if (score > 0) {
    return `Risk score ${score}; no detailed signal is attached to this merged row.`
  }

  return level === 'low' ? 'No notable anomaly signals attached.' : `${formatSignalLabel(level)} risk from backend scoring.`
}

function getMergedFlagSummaries(item: ReviewQueueItem) {
  const policyFlags = policyFlagsFor(item).map((flag) => ({
    className: policySeverityClass(flag.severity),
    key: `policy-${flag.rule_code}`,
    label: formatPolicyRuleLabel(flag.rule_code),
  }))
  const riskFlags = riskSignalsFor(item).map((signal) => ({
    className: riskSeverityClass[signal.severity],
    key: `risk-${signal.type}`,
    label: formatSignalLabel(signal.type),
  }))

  return [...policyFlags, ...riskFlags]
}

function policySeverityClass(severity: PolicySeverity) {
  return severity === 'critical'
    ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
    : severity === 'high'
      ? 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
      : severity === 'medium'
        ? 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'
        : 'bg-muted text-muted-foreground'
}

function formatPolicyRuleLabel(ruleCode: string) {
  const knownLabels: Record<string, string> = {
    ALCOHOL_RESTRICTED: 'Alcohol restricted',
    ENTERTAINMENT_CONTEXT_REQUIRED: 'Entertainment context required',
    PERSONAL_CARD_USE_PROHIBITED: 'Personal card use prohibited',
    PREAPPROVAL_OVER_50: 'Pre-approval evidence required',
    PREAPPROVAL_PENDING_REVIEW: 'Pending pre-approval review',
    RECEIPT_CURRENT_MONTH: 'Current-month receipt evidence',
    RECEIPT_EVIDENCE_REQUIRED: 'Receipt evidence readiness',
    RECEIPT_REQUIRED: 'Receipt evidence required',
    TICKETS_NOT_REIMBURSABLE: 'Tickets not reimbursable',
    VEHICLE_DEBIT_REVIEW: 'Vehicle debit review',
  }

  return knownLabels[ruleCode] ?? formatSignalLabel(ruleCode)
}

function policyFlagsFor(item: ReviewQueueItem) {
  return item.policy_flags ?? []
}

function riskSignalsFor(item: ReviewQueueItem) {
  return item.risk_signals ?? []
}

function groupReviewQueueItems(items: ReviewQueueItem[]): ReviewQueueGroup[] {
  const groups = new Map<string, ReviewQueueItem[]>()

  for (const item of items) {
    const key = reviewGroupKey(item)
    groups.set(key, [...(groups.get(key) ?? []), item])
  }

  return Array.from(groups.entries())
    .map(([key, groupItems]) => {
      const sortedItems = sortQueueItems(groupItems)
      const representative = sortedItems[0]
      const highestReviewLevel = highestPolicySeverity(sortedItems.map((item) => item.review_level))
      const highestRiskLevel = highestRiskSeverity(sortedItems.map((item) => item.risk_level ?? 'low'))

      return {
        amountBreakdown: summarizeGroupAmounts(sortedItems),
        category: representative.category,
        department: representative.department,
        employee: representative.employee,
        highestPolicyStatus: highestPolicyStatus(sortedItems.map((item) => item.policy_status)),
        highestReviewLevel,
        highestRiskLevel,
        items: sortedItems,
        key,
        merchant: representative.merchant,
        priority: Math.max(...sortedItems.map((item) => item.review_priority)),
        representative,
        totalAmount: sortedItems.reduce((total, item) => total + item.amount_cad, 0),
        transactionDate: representative.transaction_date,
      }
    })
    .sort((left, right) => {
      const priorityDelta = right.priority - left.priority
      if (priorityDelta !== 0) {
        return priorityDelta
      }

      return right.totalAmount - left.totalAmount
    })
}

function reviewGroupKey(item: ReviewQueueItem) {
  if (!item.merchant || !item.transaction_date || !item.employee) {
    return `transaction:${item.transaction_id}`
  }

  return [
    'review-context',
    item.employee_id ?? normalizeGroupValue(item.employee),
    item.department_id ?? normalizeGroupValue(item.department),
    normalizeGroupValue(item.merchant),
    item.transaction_date,
    normalizeGroupValue(item.category),
  ].join('|')
}

function normalizeGroupValue(value: string | null | undefined) {
  return (value ?? 'unknown').trim().toLowerCase().replace(/\s+/g, ' ')
}

function highestPolicySeverity(values: PolicySeverity[]) {
  const severityRank: Record<PolicySeverity, number> = {
    low: 1,
    medium: 2,
    high: 3,
    critical: 4,
  }

  return values.reduce<PolicySeverity>(
    (highest, value) => (severityRank[value] > severityRank[highest] ? value : highest),
    'low',
  )
}

function highestRiskSeverity(values: RiskLevel[]) {
  const severityRank: Record<RiskLevel, number> = {
    low: 1,
    medium: 2,
    high: 3,
    critical: 4,
  }

  return values.reduce<RiskLevel>(
    (highest, value) => (severityRank[value] > severityRank[highest] ? value : highest),
    'low',
  )
}

function highestPolicyStatus(values: Array<PolicyStatus | null>) {
  const statusRank: Record<PolicyStatus, number> = {
    compliant: 0,
    excluded_non_expense: 1,
    review_required: 2,
    context_needed: 3,
    approval_evidence_needed: 4,
    policy_violation: 5,
  }

  return values.reduce<PolicyStatus | null>((highest, value) => {
    if (!value) {
      return highest
    }
    if (!highest || statusRank[value] > statusRank[highest]) {
      return value
    }
    return highest
  }, null)
}

function summarizeGroupAmounts(items: ReviewQueueItem[]) {
  const amountCounts = new Map<number, number>()
  for (const item of items) {
    amountCounts.set(item.amount_cad, (amountCounts.get(item.amount_cad) ?? 0) + 1)
  }

  return Array.from(amountCounts.entries())
    .sort(([leftAmount], [rightAmount]) => rightAmount - leftAmount)
    .map(([amount, count]) => `${count} x CAD ${amount.toFixed(2)}`)
    .join(' · ')
}

function getGroupFlagSummaries(group: ReviewQueueGroup) {
  const summaries = new Map<string, ReturnType<typeof getMergedFlagSummaries>[number]>()

  for (const item of group.items) {
    for (const flag of getMergedFlagSummaries(item)) {
      summaries.set(flag.key, flag)
    }
  }

  return Array.from(summaries.values())
}

function getExactDuplicateCount(items: ReviewQueueItem[]) {
  const exactMatches = new Map<string, number>()
  for (const item of items) {
    const key = [normalizeGroupValue(item.merchant), item.transaction_date ?? 'unknown-date', item.amount_cad.toFixed(2)].join('|')
    exactMatches.set(key, (exactMatches.get(key) ?? 0) + 1)
  }

  return Array.from(exactMatches.values()).reduce((count, matches) => {
    if (matches < 2) {
      return count
    }
    return count + (matches * (matches - 1)) / 2
  }, 0)
}

function sortQueueItems(items: ReviewQueueItem[]) {
  return [...items].sort((left, right) => {
    const priorityDelta = right.review_priority - left.review_priority
    if (priorityDelta !== 0) {
      return priorityDelta
    }

    return right.amount_cad - left.amount_cad
  })
}

function formatDuration(durationMs: number) {
  if (durationMs < 1000) {
    return `${durationMs} ms`
  }

  return `${(durationMs / 1000).toFixed(1)} s`
}
