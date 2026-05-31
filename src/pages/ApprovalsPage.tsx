import {
  Clock3,
  CheckCircle2,
  FileCheck2,
  Info,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  UserRound,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  createApprovalRequest,
  decideApprovalRequest,
  getApprovalRequest,
  listApprovals,
  listReviewQueueItems,
  type ApprovalDecision,
  type ApprovalRequestDetail,
  type ApprovalRequestItem,
  type ApprovalStatus,
  type ReviewQueueItem,
} from '@/lib/api/backendClient'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { useUiPreferences } from '@/lib/ui/preferences'

const actionablePolicyStatuses = new Set(['approval_evidence_needed', 'review_required', 'context_needed', 'policy_violation'])
const activeApprovalStatuses = new Set<ApprovalStatus>(['draft', 'requested'])
const approvalsPageSize = 25
const approvalCandidatesPageSize = 25

type ReviewApprovalGroup = {
  key: string
  items: ReviewQueueItem[]
  representative: ReviewQueueItem
  totalAmount: number
  transactionIds: string[]
  priority: number
}

type SavedApprovalGroup = {
  key: string
  items: ApprovalRequestItem[]
  representative: ApprovalRequestItem
  totalAmount: number
  transactionIds: string[]
}

export function ApprovalsPage() {
  const { locale, t } = useUiPreferences()
  const detailPanelRef = useRef<HTMLElement | null>(null)
  const linkedApprovalId = useMemo(() => new URLSearchParams(window.location.search).get('approval'), [])
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([])
  const [approvals, setApprovals] = useState<ApprovalRequestItem[]>([])
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRequestDetail | null>(null)
  const [statusFilter, setStatusFilter] = useState<ApprovalStatus | ''>('')
  const [actor, setActor] = useState('Finance Manager')
  const [decisionNote, setDecisionNote] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMoreApprovals, setIsLoadingMoreApprovals] = useState(false)
  const [isLoadingMoreCandidates, setIsLoadingMoreCandidates] = useState(false)
  const [hasMoreApprovals, setHasMoreApprovals] = useState(false)
  const [hasMoreCandidates, setHasMoreCandidates] = useState(false)
  const [isCreating, setIsCreating] = useState<string | null>(null)
  const [isDeciding, setIsDeciding] = useState<ApprovalDecision | null>(null)
  const [error, setError] = useState<string | null>(null)
  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: 'CAD',
      }),
    [locale],
  )
  const actionableReviewItems = useMemo(() => reviewItems.filter(isApprovalCandidate), [reviewItems])
  const actionableReviewGroups = useMemo(() => groupReviewApprovalCandidates(actionableReviewItems), [actionableReviewItems])
  const activeApprovals = useMemo(() => approvals.filter((approval) => activeApprovalStatuses.has(approval.status)), [approvals])
  const savedApprovalGroups = useMemo(() => groupSavedApprovals(approvals), [approvals])
  const activeApprovalGroups = useMemo(() => groupSavedApprovals(activeApprovals), [activeApprovals])
  const decidedApprovals = savedApprovalGroups.length - activeApprovalGroups.length
  const requestedApprovals = useMemo(() => groupSavedApprovals(approvals.filter((approval) => approval.status === 'requested')).length, [approvals])
  const workflowStages = useMemo(
    () => [
      {
        label: 'Needs manager packet',
        value: actionableReviewGroups.length,
        detail: 'Review clusters still waiting to be opened',
        tone: 'warn' as const,
      },
      {
        label: 'Packet assembled',
        value: savedApprovalGroups.length,
        detail: 'Approval clusters now have packet shells',
        tone: 'neutral' as const,
      },
      {
        label: 'Pending decision',
        value: requestedApprovals,
        detail: 'Packets ready for a manager decision',
        tone: 'warn' as const,
      },
      {
        label: 'Decision logged',
        value: decidedApprovals,
        detail: 'Packets already closed out',
        tone: 'good' as const,
      },
    ],
    [actionableReviewGroups.length, savedApprovalGroups.length, requestedApprovals, decidedApprovals],
  )
  const assistantContext = useMemo(
    () => ({
      routeId: 'approvals' as const,
      title: 'Approvals',
      summary: `Managing ${activeApprovalGroups.length} active approval clusters and ${actionableReviewGroups.length} queue clusters that still need a manager.`,
      filters: {
        status: statusFilter || null,
      },
      focus: selectedApproval
        ? {
            type: 'approval_request',
            id: selectedApproval.id,
            label: selectedApproval.merchant ?? selectedApproval.employee_name ?? selectedApproval.id,
            status: selectedApproval.status,
          }
        : null,
      focusEntities: selectedApproval
        ? [
            {
              type: 'approval_request',
              id: selectedApproval.id,
              label: selectedApproval.merchant ?? selectedApproval.employee_name ?? selectedApproval.id,
              status: selectedApproval.status,
              attributes: {
                requested_amount_cad: selectedApproval.requested_amount_cad,
                policy_status: selectedApproval.policy_status,
                risk_level: selectedApproval.risk_level,
              },
            },
          ]
        : [],
      visibleEntities: [
        ...activeApprovalGroups.slice(0, 5).map((group) => {
          const approval = group.representative
          return {
          type: 'approval_request',
          id: approval.id,
          label: approval.merchant ?? approval.employee_name ?? approval.id,
          status: approval.status,
          attributes: {
            requested_amount_cad: approval.requested_amount_cad,
            policy_status: approval.policy_status,
            risk_level: approval.risk_level,
          },
        }}),
        ...actionableReviewGroups.slice(0, 5).map((group) => {
          const item = group.representative
          return {
          type: 'review_queue_item',
          id: item.id ?? item.transaction_id,
          label: item.merchant ?? item.employee ?? item.transaction_id,
          status: item.review_level,
          attributes: {
            amount_cad: item.amount_cad,
            policy_status: item.policy_status,
            risk_level: item.risk_level,
          },
        }}),
      ],
      metrics: {
        actionable: actionableReviewGroups.length,
        active: activeApprovalGroups.length,
        decided: decidedApprovals,
      },
      availableViews: ['active approvals', 'approval candidates', 'decision detail'],
      suggestions: [
        selectedApproval ? `Summarize approval ${selectedApproval.merchant ?? selectedApproval.id}` : 'What is waiting for approval?',
        'What should the manager focus on here?',
      ],
    }),
    [activeApprovalGroups, actionableReviewGroups, decidedApprovals, selectedApproval, statusFilter],
  )
  useAssistantPageContext(assistantContext)

  async function focusApproval(approval: ApprovalRequestItem | ApprovalRequestDetail) {
    setError(null)
    setActor((current) => approval.approver_name ?? current)
    setDecisionNote('')

    try {
      if ('context_snapshot' in approval) {
        setSelectedApproval(approval)
        return
      }
      setSelectedApproval(await getApprovalRequest(approval.id))
    } catch (detailError) {
      setSelectedApproval(approval as ApprovalRequestDetail)
      setError(detailError instanceof Error ? detailError.message : 'Could not load approval detail.')
    }
  }

  async function loadApprovalWorkspace(nextStatus = statusFilter) {
    setIsLoading(true)
    setError(null)

    try {
      const [approvalResponse, queueResponse] = await Promise.all([
        listApprovals({ status: nextStatus || undefined, limit: approvalsPageSize }),
        listReviewQueueItems({ queue_status: 'open', limit: approvalCandidatesPageSize }),
      ])
      setApprovals(approvalResponse.approvals)
      setReviewItems(queueResponse)
      setHasMoreApprovals(approvalResponse.approvals.length === approvalsPageSize)
      setHasMoreCandidates(queueResponse.length === approvalCandidatesPageSize)
      setSelectedApproval((current) => {
        if (!current) {
          return null
        }
        const refreshed = approvalResponse.approvals.find((approval) => approval.id === current.id)
        return refreshed ? ({ ...current, ...refreshed } as ApprovalRequestDetail) : current
      })
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load approval workflow.')
    } finally {
      setIsLoading(false)
    }
  }

  async function loadMoreApprovalCandidates() {
    setIsLoadingMoreCandidates(true)
    setError(null)

    try {
      const queueResponse = await listReviewQueueItems({
        queue_status: 'open',
        limit: approvalCandidatesPageSize,
        offset: reviewItems.length,
      })
      setReviewItems((currentItems) => [...currentItems, ...queueResponse])
      setHasMoreCandidates(queueResponse.length === approvalCandidatesPageSize)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load more approval candidates.')
    } finally {
      setIsLoadingMoreCandidates(false)
    }
  }

  async function loadMoreApprovals() {
    setIsLoadingMoreApprovals(true)
    setError(null)

    try {
      const approvalResponse = await listApprovals({
        status: statusFilter || undefined,
        limit: approvalsPageSize,
        offset: approvals.length,
      })
      setApprovals((currentApprovals) => [...currentApprovals, ...approvalResponse.approvals])
      setHasMoreApprovals(approvalResponse.approvals.length === approvalsPageSize)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load more approvals.')
    } finally {
      setIsLoadingMoreApprovals(false)
    }
  }

  async function createFromReviewItem(item: ReviewQueueItem) {
    setIsCreating(item.id ?? item.transaction_id)
    setError(null)

    try {
      const approval = await createApprovalRequest({
        review_queue_item_id: item.id,
        transaction_id: item.transaction_id,
        actor,
      })
      setSelectedApproval(approval)
      setActor(approval.approver_name ?? actor)
      setDecisionNote('')
      await loadApprovalWorkspace()
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Could not create approval request.')
    } finally {
      setIsCreating(null)
    }
  }

  async function decide(decision: ApprovalDecision) {
    if (!selectedApproval) {
      return
    }

    setIsDeciding(decision)
    setError(null)

    try {
      const updated = await decideApprovalRequest(selectedApproval.id, {
        decision,
        actor: actor.trim() || selectedApproval.approver_name || 'Finance Manager',
        note: decisionNote.trim() || null,
      })
      setSelectedApproval(updated)
      setDecisionNote('')
      await loadApprovalWorkspace()
    } catch (decisionError) {
      setError(decisionError instanceof Error ? decisionError.message : 'Could not save approval decision.')
    } finally {
      setIsDeciding(null)
    }
  }

  useEffect(() => {
    let ignore = false

    async function loadInitial() {
      try {
        const [approvalResponse, queueResponse] = await Promise.all([
          listApprovals({ limit: approvalsPageSize }),
          listReviewQueueItems({ queue_status: 'open', limit: approvalCandidatesPageSize }),
        ])
        if (!ignore) {
          setApprovals(approvalResponse.approvals)
          setReviewItems(queueResponse)
          setHasMoreApprovals(approvalResponse.approvals.length === approvalsPageSize)
          setHasMoreCandidates(queueResponse.length === approvalCandidatesPageSize)
          if (linkedApprovalId) {
            try {
              const linkedApproval = await getApprovalRequest(linkedApprovalId)
              if (!ignore) {
                setSelectedApproval(linkedApproval)
                setActor(linkedApproval.approver_name ?? 'Finance Manager')
              }
            } catch (linkedError) {
              if (!ignore) {
                setError(linkedError instanceof Error ? linkedError.message : 'Could not load linked approval detail.')
              }
            }
          }
        }
      } catch (loadError) {
        if (!ignore) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load approval workflow.')
        }
      } finally {
        if (!ignore) {
          setIsLoading(false)
        }
      }
    }

    void loadInitial()

    return () => {
      ignore = true
    }
  }, [linkedApprovalId])

  useEffect(() => {
    if (!selectedApproval || !detailPanelRef.current) {
      return
    }

    const frame = window.requestAnimationFrame(() => {
      detailPanelRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [selectedApproval])

  return (
    <PageScaffold
      eyebrow={t('approvals.eyebrow')}
      title={t('approvals.title')}
      description={t('approvals.description')}
    >
      <section className="surface-panel p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileCheck2 className="size-4" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-semibold text-foreground">{t('approvals.waitingTitle')}</p>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t('approvals.waitingBody')}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              className="h-9 rounded-lg border border-input bg-background px-2 text-sm text-foreground"
              value={statusFilter}
              onChange={(event) => {
                const nextStatus = event.target.value as ApprovalStatus | ''
                setStatusFilter(nextStatus)
                void loadApprovalWorkspace(nextStatus)
              }}
              aria-label={t('approvals.filterStatus')}
            >
              <option value="">{t('approvals.allApprovals')}</option>
              <option value="requested">{t('approvals.requested')}</option>
              <option value="approved">{t('approvals.approved')}</option>
              <option value="denied">{t('approvals.denied')}</option>
              <option value="cancelled">{t('approvals.cancelled')}</option>
            </select>
            <Button type="button" variant="outline" onClick={() => void loadApprovalWorkspace()} disabled={isLoading}>
              <RefreshCw className="size-4" aria-hidden="true" />
              {t('approvals.refresh')}
            </Button>
          </div>
        </div>

        {error ? <p className="mt-3 rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">{error}</p> : null}

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label={t('approvals.needsDecision')} value={actionableReviewGroups.length} locale={locale} />
          <MetricCard label={t('approvals.openApprovals')} value={activeApprovalGroups.length} locale={locale} />
          <MetricCard label={t('approvals.decided')} value={decidedApprovals} locale={locale} />
          <MetricCard
            label={t('approvals.urgent')}
            value={actionableReviewGroups.filter((group) => group.representative.review_level === 'high' || group.representative.review_level === 'critical').length}
            locale={locale}
          />
        </div>

        <div className="mt-4 flex justify-center">
          <div className="w-full max-w-5xl rounded-2xl border border-border/70 bg-background/65 p-4">
            <div className="flex items-center gap-2">
              <Clock3 className="size-4 text-primary" aria-hidden="true" />
              <p className="text-sm font-semibold text-foreground">Workflow progression</p>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {workflowStages.map((stage) => (
                <ApprovalWorkflowStageCard key={stage.label} detail={stage.detail} label={stage.label} locale={locale} tone={stage.tone} value={stage.value} />
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:items-start xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
        <section className="surface-panel self-start overflow-hidden">
          <div className="border-b border-border/70 p-4">
            <p className="text-sm font-semibold text-foreground">{t('approvals.managerDecisionTitle')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('approvals.managerDecisionBody')}</p>
          </div>

          {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('approvals.loadingCandidates')}</p> : null}
          {!isLoading && actionableReviewGroups.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">{t('approvals.noManagerWaiting')}</p>
          ) : null}

          <div className="max-h-[38rem] divide-y divide-border/70 overflow-y-auto">
            {actionableReviewGroups.map((group) => {
              const item = group.representative
              return (
              <article key={group.key} className="p-4">
                <div className="panel-reveal-soft rounded-2xl border border-border/70 bg-background/70 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-foreground">{item.merchant ?? 'Unknown merchant'}</p>
                      {group.items.length > 1 ? <span className="status-chip bg-primary/10 text-primary">{group.items.length} linked rows</span> : null}
                      <StatusPill value={item.policy_status ?? 'review_required'} />
                      <RiskPill value={item.risk_level ?? 'low'} />
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {item.employee ?? t('transactions.syntheticEmployee')} · {item.department ?? t('transactions.syntheticDepartment')} · {item.transaction_date ?? '-'}
                    </p>
                    {group.items.length > 1 ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Cluster total {currencyFormatter.format(group.totalAmount)} across {group.items.length} transactions.
                      </p>
                    ) : null}
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                      {item.reviewer_brief?.summary ?? item.ai_context ?? item.next_action}
                    </p>
                    <div className="mt-3 grid gap-2 sm:grid-cols-3">
                      <QueueSignalCard
                        label="Policy packet"
                        tone={item.policy_flags.length > 0 ? 'warn' : 'good'}
                        value={item.policy_flags.length > 0 ? `${item.policy_flags.length} flag${item.policy_flags.length === 1 ? '' : 's'}` : 'Grounded'}
                      />
                      <QueueSignalCard
                        label="Risk read"
                        tone={item.risk_level === 'high' || item.risk_level === 'critical' ? 'bad' : item.risk_level === 'medium' ? 'warn' : 'good'}
                        value={`${formatLabel(item.risk_level ?? 'low')} risk`}
                      />
                      <QueueSignalCard label="Next move" tone="neutral" value={item.next_action} />
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.policy_flags.slice(0, 2).map((flag) => (
                        <span key={flag.rule_code} className="status-chip bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100">
                          {formatLabel(flag.rule_code)}
                        </span>
                      ))}
                      {item.risk_signals.slice(0, 2).map((signal) => (
                        <span key={signal.type} className="status-chip bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100">
                          {formatLabel(signal.type)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-start gap-2 lg:items-end">
                    <p className="text-lg font-semibold tabular-nums text-foreground">{currencyFormatter.format(group.totalAmount)}</p>
                    <span className="text-xs text-muted-foreground">{t('approvals.priority').replace('{value}', String(group.priority))}</span>
                    <Button
                      type="button"
                      onClick={() => void createFromReviewItem(item)}
                      disabled={isCreating === (item.id ?? item.transaction_id)}
                    >
                      <Send className="size-4" aria-hidden="true" />
                      {isCreating === (item.id ?? item.transaction_id) ? t('approvals.creating') : group.items.length > 1 ? 'Open cluster' : t('approvals.openApproval')}
                    </Button>
                  </div>
                </div>
                </div>
              </article>
            )})}
          </div>
          {hasMoreCandidates ? (
            <div className="border-t border-border/70 p-4">
              <Button type="button" variant="outline" onClick={() => void loadMoreApprovalCandidates()} disabled={isLoadingMoreCandidates}>
                {isLoadingMoreCandidates ? 'Loading more...' : 'Load more candidates'}
              </Button>
            </div>
          ) : null}
        </section>

        <section className="grid self-start gap-4">
          <section className="surface-panel overflow-hidden">
            <div className="border-b border-border/70 p-4">
              <p className="text-sm font-semibold text-foreground">{t('approvals.savedApprovalsTitle')}</p>
              <p className="mt-1 text-sm text-muted-foreground">{t('approvals.savedApprovalsBody')}</p>
            </div>
            {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('approvals.loadingApprovals')}</p> : null}
            {!isLoading && savedApprovalGroups.length === 0 ? <p className="p-4 text-sm text-muted-foreground">{t('approvals.noApprovals')}</p> : null}
            <div className="max-h-[24rem] divide-y divide-border/70 overflow-y-auto">
              {savedApprovalGroups.map((group) => {
                const approval = group.representative
                return (
                <button
                  key={group.key}
                  type="button"
                  className={`w-full px-4 py-3 text-left transition ${
                    group.items.some((item) => item.id === selectedApproval?.id) ? 'bg-primary/8' : 'bg-background hover:bg-muted/70'
                  }`}
                  onClick={() => void focusApproval(approval)}
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-foreground">{approval.merchant ?? 'Unknown merchant'}</span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {approval.employee_name ?? t('transactions.syntheticEmployee')} · {approval.department_name ?? t('transactions.syntheticDepartment')}
                      </span>
                      {group.items.length > 1 ? (
                        <span className="mt-1 block text-xs text-primary">{group.items.length} linked approvals share this decision cluster</span>
                      ) : null}
                    </span>
                    <span className="text-sm font-medium tabular-nums text-foreground">
                      {currencyFormatter.format(group.totalAmount)}
                    </span>
                  </span>
                  <span className="mt-2 flex flex-wrap items-center gap-1.5">
                    <ApprovalStatusPill status={approval.status} />
                    {approval.ai_recommendation ? <RecommendationPill value={approval.ai_recommendation.recommendation} /> : null}
                  </span>
                  <span className="mt-2 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                    <span>{approval.transaction_date ?? 'Date pending'}</span>
                    <span>{approval.id}</span>
                  </span>
                </button>
              )})}
            </div>
            {hasMoreApprovals ? (
              <div className="border-t border-border/70 p-4">
                <Button type="button" variant="outline" onClick={() => void loadMoreApprovals()} disabled={isLoadingMoreApprovals}>
                  {isLoadingMoreApprovals ? 'Loading more...' : 'Load more approvals'}
                </Button>
              </div>
            ) : null}
          </section>
        </section>
      </section>

      <ApprovalDetailPanel
        actor={actor}
        currencyFormatter={currencyFormatter}
        decisionNote={decisionNote}
        isDeciding={isDeciding}
        linkedApprovalId={linkedApprovalId}
        onActorChange={setActor}
        onDecision={decide}
        onDecisionNoteChange={setDecisionNote}
        panelRef={detailPanelRef}
        selectedApproval={selectedApproval}
      />
    </PageScaffold>
  )
}

function ApprovalDetailPanel({
  actor,
  currencyFormatter,
  decisionNote,
  isDeciding,
  linkedApprovalId,
  onActorChange,
  onDecision,
  onDecisionNoteChange,
  panelRef,
  selectedApproval,
}: {
  actor: string
  currencyFormatter: Intl.NumberFormat
  decisionNote: string
  isDeciding: ApprovalDecision | null
  linkedApprovalId: string | null
  onActorChange: (value: string) => void
  onDecision: (decision: ApprovalDecision) => void
  onDecisionNoteChange: (value: string) => void
  panelRef: React.RefObject<HTMLElement | null>
  selectedApproval: ApprovalRequestDetail | null
}) {
  const { t } = useUiPreferences()

  if (!selectedApproval) {
    return null
  }

  const recommendation = selectedApproval.ai_recommendation
  const approvalExplanation = selectedApproval.approval_explanation
  const canDecide = activeApprovalStatuses.has(selectedApproval.status)
  const keyReasons = selectedApproval.reviewer_brief?.key_reasons ?? []

  return (
    <section ref={panelRef} className="surface-panel panel-reveal overflow-hidden scroll-mt-6">
      <div className="border-b border-border/70 bg-gradient-to-br from-primary/10 via-background to-background p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-foreground">{selectedApproval.merchant ?? 'Unknown merchant'}</p>
              {linkedApprovalId === selectedApproval.id ? <span className="status-chip bg-primary/12 text-primary">Opened from report</span> : null}
            </div>
            <p className="text-sm text-muted-foreground">
              {selectedApproval.employee_name ?? t('transactions.syntheticEmployee')} · {selectedApproval.department_name ?? t('transactions.syntheticDepartment')} · {selectedApproval.transaction_date ?? '-'}
            </p>
            <div className="flex flex-wrap gap-1.5">
              <ApprovalStatusPill status={selectedApproval.status} />
              {recommendation ? <RecommendationPill value={recommendation.recommendation} /> : null}
              <StatusPill value={selectedApproval.policy_status ?? 'compliant'} />
              <RiskPill value={selectedApproval.risk_level ?? 'low'} />
            </div>
          </div>

          <div className="grid min-w-[220px] gap-2 sm:grid-cols-3 xl:min-w-[320px]">
            <PacketStatCard label="Requested" value={currencyFormatter.format(selectedApproval.requested_amount_cad)} />
            <PacketStatCard label="Missing info" value={String(recommendation?.missing_information.length ?? 0)} />
            <PacketStatCard label="Signals" value={String(selectedApproval.risk_signals.length + selectedApproval.policy_flags.length)} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-4">
        {recommendation ? (
          <section className="rounded-2xl border border-primary/15 bg-primary/6 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Info className="size-4 text-primary" aria-hidden="true" />
              {t('approvals.advisoryRecommendation')}
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{recommendation.rationale}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <FactList title={t('approvals.groundedInputs')} items={recommendation.grounded_inputs} />
              <FactList title={t('approvals.missingInformation')} items={recommendation.missing_information} empty={t('approvals.noneRecorded')} />
            </div>
          </section>
        ) : null}

        {approvalExplanation ? (
          <section className="rounded-2xl border border-border/70 bg-background/65 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Sparkles className="size-4 text-primary" aria-hidden="true" />
                  Why this recommendation?
                </div>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{approvalExplanation.summary}</p>
              </div>
              <div className="grid min-w-[220px] gap-2 sm:grid-cols-2 lg:grid-cols-1">
                <PacketStatCard label="Decision" value={formatLabel(approvalExplanation.decision)} />
                <PacketStatCard label="Confidence" value={formatLabel(approvalExplanation.confidence)} />
                <PacketStatCard label="Reversal paths" value={String(approvalExplanation.would_change_outcome_if.length)} />
              </div>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
              <div className="grid gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Blocking reasons</p>
                  {approvalExplanation.blocking_reasons.length === 0 ? (
                    <p className="mt-2 text-sm text-muted-foreground">No blocking reasons are attached to this packet.</p>
                  ) : (
                    <div className="mt-2 grid gap-2">
                      {approvalExplanation.blocking_reasons.map((reason) => (
                        <ExplanationReasonCard key={`${reason.label}-${reason.detail}`} reason={reason} />
                      ))}
                    </div>
                  )}
                </div>

                <FactList title="Supporting evidence" items={approvalExplanation.supporting_evidence} empty="No grounded evidence recorded." />
              </div>

              <div className="grid gap-4">
                <FactList title="What would change this outcome?" items={approvalExplanation.would_change_outcome_if} empty="No outcome changes suggested." />
                <ClauseList clauses={approvalExplanation.cited_policy_clauses} />
              </div>
            </div>
          </section>
        ) : null}

        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(340px,0.92fr)]">
          <div className="grid gap-4">
            {selectedApproval.reviewer_brief ? (
              <section className="rounded-2xl border border-border/70 bg-background/70 p-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="size-4 text-primary" aria-hidden="true" />
                  <p className="text-sm font-semibold text-foreground">{t('approvals.reviewerBrief')}</p>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{selectedApproval.reviewer_brief.summary}</p>
                {keyReasons.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {keyReasons.slice(0, 4).map((reason) => (
                      <span key={reason} className="status-chip bg-muted text-muted-foreground">
                        {reason}
                      </span>
                    ))}
                  </div>
                ) : null}
                <p className="mt-3 text-xs leading-5 text-muted-foreground">{selectedApproval.reviewer_brief.advisory_notice}</p>
              </section>
            ) : null}

            <div className="grid gap-3 lg:grid-cols-2">
              <BudgetPanel approval={selectedApproval} currencyFormatter={currencyFormatter} />
              <SpendHistoryPanel approval={selectedApproval} currencyFormatter={currencyFormatter} />
            </div>
          </div>

          {canDecide ? (
            <section className="rounded-2xl border border-border/70 bg-background/80 p-4 xl:sticky xl:top-4">
              <div className="flex items-center gap-2">
                <UserRound className="size-4 text-primary" aria-hidden="true" />
                <p className="text-sm font-semibold text-foreground">{t('approvals.decision')}</p>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">Capture the final approver and log the rationale that should travel with this packet.</p>
              <div className="mt-4 grid gap-3">
                <div className="grid gap-2">
                  <input
                    className="h-10 rounded-xl border border-input bg-background px-3 text-sm text-foreground"
                    value={actor}
                    onChange={(event) => onActorChange(event.target.value)}
                    placeholder={selectedApproval.approver_name ?? 'Finance Manager'}
                  />
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <PacketStatCard label="Requested amount" value={currencyFormatter.format(selectedApproval.requested_amount_cad)} />
                  <PacketStatCard label="Signals" value={String(selectedApproval.risk_signals.length + selectedApproval.policy_flags.length)} />
                </div>
                <textarea
                  className="min-h-20 resize-y rounded-xl border border-input bg-background p-3 text-sm leading-6 text-foreground"
                  value={decisionNote}
                  onChange={(event) => onDecisionNoteChange(event.target.value)}
                  placeholder={t('approvals.decisionNote')}
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  <Button type="button" onClick={() => onDecision('approved')} disabled={Boolean(isDeciding)} className="h-11 justify-center">
                    <CheckCircle2 className="size-4" aria-hidden="true" />
                    {isDeciding === 'approved' ? t('approvals.approving') : t('actions.approve')}
                  </Button>
                  <Button type="button" variant="destructive" onClick={() => onDecision('denied')} disabled={Boolean(isDeciding)} className="h-11 justify-center">
                    <XCircle className="size-4" aria-hidden="true" />
                    {isDeciding === 'denied' ? t('approvals.denying') : t('approvals.deny')}
                  </Button>
                </div>
              </div>
            </section>
          ) : (
            <section className="rounded-2xl border border-emerald-300/50 bg-emerald-100/50 p-4 text-sm text-emerald-900 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-100 xl:sticky xl:top-4">
              <p className="font-semibold">Decision already saved</p>
              <p className="mt-2 leading-6">
                {t('approvals.decisionSaved')
                  .replace('{actor}', selectedApproval.decided_by ?? 'approver')
                  .replace('{timestamp}', selectedApproval.decided_at ? ` at ${selectedApproval.decided_at}` : '')}
              </p>
            </section>
          )}
        </div>
      </div>
    </section>
  )
}

function MetricCard({ label, locale, value }: { label: string; locale: string; value: number }) {
  return (
    <div className="subtle-panel p-3">
      <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value.toLocaleString(locale)}</p>
    </div>
  )
}

function ApprovalWorkflowStageCard({
  detail,
  label,
  locale,
  tone,
  value,
}: {
  detail: string
  label: string
  locale: string
  tone: 'good' | 'warn' | 'neutral'
  value: number
}) {
  const toneClass =
    tone === 'good'
      ? 'text-emerald-700 dark:text-emerald-100'
      : tone === 'warn'
        ? 'text-amber-800 dark:text-amber-100'
        : 'text-foreground'

  return (
    <div className="rounded-2xl border border-border/70 bg-muted/35 p-3">
      <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${toneClass}`}>{value.toLocaleString(locale)}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</p>
    </div>
  )
}

function QueueSignalCard({
  label,
  tone,
  value,
}: {
  label: string
  tone: 'good' | 'warn' | 'bad' | 'neutral'
  value: string
}) {
  const toneClass =
    tone === 'good'
      ? 'text-emerald-700 dark:text-emerald-100'
      : tone === 'warn'
        ? 'text-amber-800 dark:text-amber-100'
        : tone === 'bad'
          ? 'text-red-700 dark:text-red-100'
          : 'text-foreground'

  return (
    <div className="rounded-xl border border-border/70 bg-muted/35 px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className={`mt-1 text-sm font-medium ${toneClass}`}>{value}</p>
    </div>
  )
}

function PacketStatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/75 px-3 py-2.5">
      <p className="text-[11px] font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className="mt-1 text-base font-semibold text-foreground">{value}</p>
    </div>
  )
}

function BudgetPanel({ approval, currencyFormatter }: { approval: ApprovalRequestItem; currencyFormatter: Intl.NumberFormat }) {
  const { t } = useUiPreferences()
  const budget = approval.budget_status

  return (
    <section className="rounded-lg border border-border/70 bg-background/70 p-3">
      <p className="text-sm font-semibold text-foreground">{t('approvals.budgetSnapshot')}</p>
      {!budget ? <p className="mt-2 text-sm text-muted-foreground">{t('approvals.budgetUnavailable')}</p> : null}
      {budget ? (
        <div className="mt-3 grid gap-2 text-sm">
          <FactLine label={t('approvals.monthRemaining')} value={currencyFormatter.format(budget.monthly_remaining_cad)} />
          <FactLine label={t('approvals.quarterRemaining')} value={currencyFormatter.format(budget.quarterly_remaining_cad)} />
          <FactLine label={t('approvals.quarterSpend')} value={currencyFormatter.format(budget.quarter_to_date_spend_cad)} />
        </div>
      ) : null}
    </section>
  )
}

function SpendHistoryPanel({ approval, currencyFormatter }: { approval: ApprovalRequestItem; currencyFormatter: Intl.NumberFormat }) {
  const { t } = useUiPreferences()
  const history = approval.spend_history

  return (
    <section className="rounded-lg border border-border/70 bg-background/70 p-3">
      <p className="text-sm font-semibold text-foreground">{t('approvals.spendHistory')}</p>
      {!history ? <p className="mt-2 text-sm text-muted-foreground">{t('approvals.spendHistoryUnavailable')}</p> : null}
      {history ? (
        <div className="mt-3 grid gap-2 text-sm">
          <FactLine label={t('approvals.transactions')} value={String(history.transaction_count)} />
          <FactLine label={t('approvals.totalSpend')} value={currencyFormatter.format(history.total_spend_cad)} />
          <FactLine label={t('approvals.priorApprovals')} value={`${history.prior_approved_count}/${history.prior_approval_count}`} />
        </div>
      ) : null}
    </section>
  )
}

function FactLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-muted px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  )
}

function FactList({ empty = 'None.', items, title }: { empty?: string; items: string[]; title: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{title}</p>
      {items.length === 0 ? <p className="mt-1 text-sm text-muted-foreground">{empty}</p> : null}
      <ul className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={item} className="text-sm leading-5 text-muted-foreground">
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ExplanationReasonCard({
  reason,
}: {
  reason: {
    label: string
    severity: 'info' | 'warning' | 'blocking'
    detail: string
  }
}) {
  const toneClass =
    reason.severity === 'blocking'
      ? 'border-red-300/60 bg-red-100/60 dark:border-red-400/20 dark:bg-red-400/10'
      : reason.severity === 'warning'
        ? 'border-amber-300/60 bg-amber-100/60 dark:border-amber-400/20 dark:bg-amber-400/10'
        : 'border-border/70 bg-background/70'
  const labelClass =
    reason.severity === 'blocking'
      ? 'text-red-700 dark:text-red-100'
      : reason.severity === 'warning'
        ? 'text-amber-800 dark:text-amber-100'
        : 'text-foreground'

  return (
    <div className={`rounded-2xl border p-3 ${toneClass}`}>
      <p className={`text-sm font-semibold ${labelClass}`}>{reason.label}</p>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">{reason.detail}</p>
    </div>
  )
}

function ClauseList({
  clauses,
}: {
  clauses: Array<{
    rule_code?: string | null
    clause_id?: string | null
    title?: string | null
    text: string
    source?: string | null
  }>
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Policy citations</p>
      {clauses.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No policy citation is attached to this packet yet.</p> : null}
      <div className="mt-2 grid gap-2">
        {clauses.map((clause) => (
          <div
            key={`${clause.rule_code ?? 'policy'}-${clause.clause_id ?? clause.text}`}
            className="rounded-2xl border border-border/70 bg-background/70 p-3"
          >
            <p className="text-sm font-semibold text-foreground">
              {clause.title ?? formatLabel(clause.rule_code ?? 'policy clause')}
            </p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{clause.text}</p>
            {(clause.source || clause.rule_code) ? (
              <p className="mt-2 text-xs text-muted-foreground">
                {[clause.rule_code ? formatLabel(clause.rule_code) : null, clause.source].filter(Boolean).join(' · ')}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function ApprovalStatusPill({ status }: { status: ApprovalStatus }) {
  const className =
    status === 'approved'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100'
      : status === 'denied' || status === 'cancelled'
        ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
      : 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'

  return <span className={`status-chip ${className}`}>{formatLabel(status)}</span>
}

function RecommendationPill({ value }: { value: string }) {
  const { t } = useUiPreferences()
  const className =
    value === 'approve'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100'
      : value === 'deny'
        ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
        : 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'

  return <span className={`status-chip ${className}`}>{t('approvals.recommend').replace('{value}', formatLabel(value))}</span>
}

function StatusPill({ value }: { value: string }) {
  return <span className="status-chip bg-muted text-muted-foreground">{formatLabel(value)}</span>
}

function RiskPill({ value }: { value: string }) {
  const className =
    value === 'critical' || value === 'high'
      ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
      : value === 'medium'
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
        : 'bg-muted text-muted-foreground'

  return (
    <span className={`status-chip ${className}`}>
      <ShieldAlert className="size-3" aria-hidden="true" />
      {formatLabel(value)} risk
    </span>
  )
}

function isApprovalCandidate(item: ReviewQueueItem) {
  if (item.queue_status !== 'open') {
    return false
  }
  if (item.policy_status && actionablePolicyStatuses.has(item.policy_status)) {
    return true
  }
  return item.risk_level === 'high' || item.risk_level === 'critical'
}

function groupReviewApprovalCandidates(items: ReviewQueueItem[]): ReviewApprovalGroup[] {
  const groups = new Map<string, ReviewQueueItem[]>()

  for (const item of items) {
    const key = item.review_group_key ?? fallbackReviewGroupKey(item)
    groups.set(key, [...(groups.get(key) ?? []), item])
  }

  return Array.from(groups.entries())
    .map(([key, groupItems]) => {
      const sortedItems = sortReviewItems(groupItems)
      const representative = sortedItems[0]
      const transactionIds = groupTransactionIds(sortedItems)

      return {
        key,
        items: sortedItems,
        representative,
        totalAmount: Number(
          (representative.review_group_total_amount_cad || sortedItems.reduce((total, item) => total + item.amount_cad, 0)).toFixed(2),
        ),
        transactionIds,
        priority: Math.max(...sortedItems.map((item) => item.review_priority)),
      }
    })
    .sort((left, right) => right.priority - left.priority || right.totalAmount - left.totalAmount)
}

function groupSavedApprovals(items: ApprovalRequestItem[]): SavedApprovalGroup[] {
  const groups = new Map<string, ApprovalRequestItem[]>()

  for (const item of items) {
    const key = item.review_group_key ?? fallbackApprovalGroupKey(item)
    groups.set(key, [...(groups.get(key) ?? []), item])
  }

  return Array.from(groups.entries())
    .map(([key, groupItems]) => {
      const sortedItems = [...groupItems].sort((left, right) => (right.created_at ?? '').localeCompare(left.created_at ?? ''))
      const representative = sortedItems[0]

      return {
        key,
        items: sortedItems,
        representative,
        totalAmount: Number(
          (representative.review_group_total_amount_cad || sortedItems.reduce((total, item) => total + item.requested_amount_cad, 0)).toFixed(2),
        ),
        transactionIds: dedupeStrings(sortedItems.flatMap((item) => item.review_group_transaction_ids.length > 0 ? item.review_group_transaction_ids : [item.transaction_id])),
      }
    })
    .sort((left, right) => (right.representative.created_at ?? '').localeCompare(left.representative.created_at ?? ''))
}

function sortReviewItems(items: ReviewQueueItem[]) {
  return [...items].sort((left, right) => right.review_priority - left.review_priority || right.amount_cad - left.amount_cad)
}

function groupTransactionIds(items: ReviewQueueItem[]) {
  return dedupeStrings(items.flatMap((item) => (item.review_group_transaction_ids.length > 0 ? item.review_group_transaction_ids : [item.transaction_id])))
}

function fallbackReviewGroupKey(item: ReviewQueueItem) {
  if (!item.merchant || !item.transaction_date || !item.employee_id) {
    return `transaction:${item.transaction_id}`
  }

  return [
    'review-context',
    normalizeGroupValue(item.employee_id),
    normalizeGroupValue(item.department_id),
    normalizeGroupValue(item.merchant),
    item.transaction_date,
    normalizeGroupValue(item.category),
  ].join('|')
}

function fallbackApprovalGroupKey(item: ApprovalRequestItem) {
  if (!item.merchant || !item.transaction_date || !item.employee_id) {
    return `transaction:${item.transaction_id}`
  }

  return [
    'review-context',
    normalizeGroupValue(item.employee_id),
    normalizeGroupValue(item.department_id),
    normalizeGroupValue(item.merchant),
    item.transaction_date,
    normalizeGroupValue(item.category),
  ].join('|')
}

function normalizeGroupValue(value: string | null | undefined) {
  return (value ?? 'unknown').trim().toLowerCase().replace(/\s+/g, ' ')
}

function dedupeStrings(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)))
}

function formatLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
