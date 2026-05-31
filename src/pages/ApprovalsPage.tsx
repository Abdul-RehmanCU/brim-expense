import {
  BadgeCheck,
  CircleDashed,
  Clock3,
  CheckCircle2,
  FileCheck2,
  Info,
  ReceiptText,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  UserRound,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

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

export function ApprovalsPage() {
  const { locale, t } = useUiPreferences()
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
  const activeApprovals = useMemo(() => approvals.filter((approval) => activeApprovalStatuses.has(approval.status)), [approvals])
  const decidedApprovals = approvals.length - activeApprovals.length
  const requestedApprovals = useMemo(() => approvals.filter((approval) => approval.status === 'requested').length, [approvals])
  const workflowStages = useMemo(
    () => [
      {
        label: 'Needs manager packet',
        value: actionableReviewItems.length,
        detail: 'Queue items still waiting to be opened',
        tone: 'warn' as const,
      },
      {
        label: 'Packet assembled',
        value: approvals.length,
        detail: 'Approval requests now have a packet shell',
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
    [actionableReviewItems.length, approvals.length, requestedApprovals, decidedApprovals],
  )
  const sarahChenActivity = useMemo(
    () =>
      actionableReviewItems.filter((item) => item.employee === 'Sarah Chen').length +
      activeApprovals.filter((approval) => approval.employee_name === 'Sarah Chen').length,
    [actionableReviewItems, activeApprovals],
  )
  const assistantContext = useMemo(
    () => ({
      routeId: 'approvals' as const,
      title: 'Approvals',
      summary: `Managing ${activeApprovals.length} active approvals and ${actionableReviewItems.length} queue items that still need a manager.`,
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
        ...activeApprovals.slice(0, 5).map((approval) => ({
          type: 'approval_request',
          id: approval.id,
          label: approval.merchant ?? approval.employee_name ?? approval.id,
          status: approval.status,
          attributes: {
            requested_amount_cad: approval.requested_amount_cad,
            policy_status: approval.policy_status,
            risk_level: approval.risk_level,
          },
        })),
        ...actionableReviewItems.slice(0, 5).map((item) => ({
          type: 'review_queue_item',
          id: item.id ?? item.transaction_id,
          label: item.merchant ?? item.employee ?? item.transaction_id,
          status: item.review_level,
          attributes: {
            amount_cad: item.amount_cad,
            policy_status: item.policy_status,
            risk_level: item.risk_level,
          },
        })),
      ],
      metrics: {
        actionable: actionableReviewItems.length,
        active: activeApprovals.length,
        decided: decidedApprovals,
      },
      availableViews: ['active approvals', 'approval candidates', 'decision detail'],
      suggestions: [
        selectedApproval ? `Summarize approval ${selectedApproval.merchant ?? selectedApproval.id}` : 'What is waiting for approval?',
        'What should the manager focus on here?',
      ],
    }),
    [activeApprovals.length, actionableReviewItems.length, decidedApprovals, selectedApproval, statusFilter],
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
          <MetricCard label={t('approvals.needsDecision')} value={actionableReviewItems.length} locale={locale} />
          <MetricCard label={t('approvals.openApprovals')} value={activeApprovals.length} locale={locale} />
          <MetricCard label={t('approvals.decided')} value={decidedApprovals} locale={locale} />
          <MetricCard
            label={t('approvals.urgent')}
            value={actionableReviewItems.filter((item) => item.review_level === 'high' || item.review_level === 'critical').length}
            locale={locale}
          />
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(260px,0.6fr)]">
          <div className="rounded-2xl border border-border/70 bg-background/65 p-4">
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

          {sarahChenActivity > 0 ? (
            <div className="panel-reveal rounded-2xl border border-primary/20 bg-primary/8 p-4">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/14 text-primary">
                  <Sparkles className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">Sarah Chen lane is active</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {sarahChenActivity.toLocaleString(locale)} approval {sarahChenActivity === 1 ? 'packet is' : 'packets are'} currently tied to Sarah Chen.
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)]">
        <section className="surface-panel overflow-hidden">
          <div className="border-b border-border/70 p-4">
            <p className="text-sm font-semibold text-foreground">{t('approvals.managerDecisionTitle')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('approvals.managerDecisionBody')}</p>
          </div>

          {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('approvals.loadingCandidates')}</p> : null}
          {!isLoading && actionableReviewItems.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">{t('approvals.noManagerWaiting')}</p>
          ) : null}

          <div className="max-h-[38rem] divide-y divide-border/70 overflow-y-auto">
            {actionableReviewItems.map((item) => (
              <article key={item.id ?? item.transaction_id} className="p-4">
                <div className="panel-reveal-soft rounded-2xl border border-border/70 bg-background/70 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold text-foreground">{item.merchant ?? 'Unknown merchant'}</p>
                      <StatusPill value={item.policy_status ?? 'review_required'} />
                      <RiskPill value={item.risk_level ?? 'low'} />
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {item.employee ?? t('transactions.syntheticEmployee')} · {item.department ?? t('transactions.syntheticDepartment')} · {item.transaction_date ?? '-'}
                    </p>
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
                    <p className="text-lg font-semibold tabular-nums text-foreground">{currencyFormatter.format(item.amount_cad)}</p>
                    <span className="text-xs text-muted-foreground">{t('approvals.priority').replace('{value}', String(item.review_priority))}</span>
                    <Button
                      type="button"
                      onClick={() => void createFromReviewItem(item)}
                      disabled={isCreating === (item.id ?? item.transaction_id)}
                    >
                      <Send className="size-4" aria-hidden="true" />
                      {isCreating === (item.id ?? item.transaction_id) ? t('approvals.creating') : t('approvals.openApproval')}
                    </Button>
                  </div>
                </div>
                </div>
              </article>
            ))}
          </div>
          {hasMoreCandidates ? (
            <div className="border-t border-border/70 p-4">
              <Button type="button" variant="outline" onClick={() => void loadMoreApprovalCandidates()} disabled={isLoadingMoreCandidates}>
                {isLoadingMoreCandidates ? 'Loading more...' : 'Load more candidates'}
              </Button>
            </div>
          ) : null}
        </section>

        <section className="grid gap-4">
          <section className="surface-panel overflow-hidden">
            <div className="border-b border-border/70 p-4">
              <p className="text-sm font-semibold text-foreground">{t('approvals.savedApprovalsTitle')}</p>
              <p className="mt-1 text-sm text-muted-foreground">{t('approvals.savedApprovalsBody')}</p>
            </div>
            {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('approvals.loadingApprovals')}</p> : null}
            {!isLoading && approvals.length === 0 ? <p className="p-4 text-sm text-muted-foreground">{t('approvals.noApprovals')}</p> : null}
            <div className="max-h-[24rem] divide-y divide-border/70 overflow-y-auto">
              {approvals.map((approval) => (
                <button
                  key={approval.id}
                  type="button"
                  className={`w-full px-4 py-3 text-left transition ${
                    selectedApproval?.id === approval.id ? 'bg-primary/8' : 'bg-background hover:bg-muted/70'
                  }`}
                  onClick={() => void focusApproval(approval)}
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-foreground">{approval.merchant ?? 'Unknown merchant'}</span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {approval.employee_name ?? t('transactions.syntheticEmployee')} · {approval.department_name ?? t('transactions.syntheticDepartment')}
                      </span>
                    </span>
                    <span className="text-sm font-medium tabular-nums text-foreground">
                      {currencyFormatter.format(approval.requested_amount_cad)}
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
              ))}
            </div>
            {hasMoreApprovals ? (
              <div className="border-t border-border/70 p-4">
                <Button type="button" variant="outline" onClick={() => void loadMoreApprovals()} disabled={isLoadingMoreApprovals}>
                  {isLoadingMoreApprovals ? 'Loading more...' : 'Load more approvals'}
                </Button>
              </div>
            ) : null}
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
            selectedApproval={selectedApproval}
          />
        </section>
      </section>
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
  selectedApproval: ApprovalRequestDetail | null
}) {
  const { t } = useUiPreferences()

  if (!selectedApproval) {
    return (
      <section className="surface-panel panel-reveal overflow-hidden p-4">
        <div className="rounded-2xl border border-dashed border-border/80 bg-background/70 p-4">
          <p className="text-sm font-semibold text-foreground">{t('approvals.decisionPacket')}</p>
          <p className="mt-2 text-sm text-muted-foreground">{t('approvals.decisionPacketBody')}</p>
          <div className="mt-4 grid gap-3">
            <PacketTimelineStep
              detail="Pick a queue item to reveal policy context, risk signals, and the decision workspace."
              icon={<ReceiptText className="size-4" aria-hidden="true" />}
              state="active"
              title="Packet reveal"
            />
            <PacketTimelineStep
              detail="A grounded recommendation, reviewer brief, and spend snapshot appear together before approval."
              icon={<Info className="size-4" aria-hidden="true" />}
              state="upcoming"
              title="Decision context"
            />
            <PacketTimelineStep
              detail="Save the manager name, log a note, and close the loop with approve or deny."
              icon={<BadgeCheck className="size-4" aria-hidden="true" />}
              state="upcoming"
              title="Final decision"
            />
          </div>
        </div>
      </section>
    )
  }

  const recommendation = selectedApproval.ai_recommendation
  const canDecide = activeApprovalStatuses.has(selectedApproval.status)
  const readinessSteps = buildApprovalReadinessSteps(selectedApproval, actor)
  const keyReasons = selectedApproval.reviewer_brief?.key_reasons ?? []

  return (
    <section className="surface-panel panel-reveal overflow-hidden">
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

          <div className="grid min-w-[220px] gap-2 sm:grid-cols-3 lg:grid-cols-1">
            <PacketStatCard label="Requested" value={currencyFormatter.format(selectedApproval.requested_amount_cad)} />
            <PacketStatCard label="Missing info" value={String(recommendation?.missing_information.length ?? 0)} />
            <PacketStatCard label="Signals" value={String(selectedApproval.risk_signals.length + selectedApproval.policy_flags.length)} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-4">
        <section className="rounded-2xl border border-border/70 bg-background/65 p-4">
          <div className="flex items-center gap-2">
            <ReceiptText className="size-4 text-primary" aria-hidden="true" />
            <p className="text-sm font-semibold text-foreground">Packet readiness</p>
          </div>
          <div className="mt-4 grid gap-3">
            {readinessSteps.map((step) => (
              <PacketTimelineStep key={step.title} detail={step.detail} icon={step.icon} state={step.state} title={step.title} />
            ))}
          </div>
        </section>

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

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <BudgetPanel approval={selectedApproval} currencyFormatter={currencyFormatter} />
              <SpendHistoryPanel approval={selectedApproval} currencyFormatter={currencyFormatter} />
            </div>

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
          </div>

          {canDecide ? (
            <section className="rounded-2xl border border-border/70 bg-background/80 p-4">
              <div className="flex items-center gap-2">
                <UserRound className="size-4 text-primary" aria-hidden="true" />
                <p className="text-sm font-semibold text-foreground">{t('approvals.decision')}</p>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">Capture the final approver and log the rationale that should travel with this packet.</p>
              <div className="mt-4 grid gap-3">
                <input
                  className="h-10 rounded-xl border border-input bg-background px-3 text-sm text-foreground"
                  value={actor}
                  onChange={(event) => onActorChange(event.target.value)}
                  placeholder={selectedApproval.approver_name ?? 'Finance Manager'}
                />
                <textarea
                  className="min-h-28 resize-y rounded-xl border border-input bg-background p-3 text-sm leading-6 text-foreground"
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
            <section className="rounded-2xl border border-emerald-300/50 bg-emerald-100/50 p-4 text-sm text-emerald-900 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-100">
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

function PacketTimelineStep({
  detail,
  icon,
  state,
  title,
}: {
  detail: string
  icon: React.ReactNode
  state: 'complete' | 'active' | 'upcoming'
  title: string
}) {
  const stateClass =
    state === 'complete'
      ? 'border-emerald-300/60 bg-emerald-100/40 text-emerald-800 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-100'
      : state === 'active'
        ? 'border-primary/25 bg-primary/8 text-primary'
        : 'border-border/70 bg-background/70 text-muted-foreground'

  const titleClass = state === 'upcoming' ? 'text-foreground' : ''

  return (
    <div className={`rounded-2xl border p-3 ${stateClass}`}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-background/85">{icon}</span>
        <div>
          <p className={`text-sm font-semibold ${titleClass}`}>{title}</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{detail}</p>
        </div>
      </div>
    </div>
  )
}

function buildApprovalReadinessSteps(approval: ApprovalRequestDetail, actor: string) {
  const hasRecommendation = Boolean(approval.ai_recommendation)
  const hasReviewerBrief = Boolean(approval.reviewer_brief?.summary)
  const isClosed = !activeApprovalStatuses.has(approval.status)

  return [
    {
      title: 'Signals attached',
      detail: `${formatLabel(approval.policy_status ?? 'compliant')} policy and ${formatLabel(approval.risk_level ?? 'low')} risk are attached to the packet.`,
      icon: <ShieldAlert className="size-4" aria-hidden="true" />,
      state: 'complete' as const,
    },
    {
      title: 'Manager packet assembled',
      detail: hasRecommendation || hasReviewerBrief ? 'Recommendation, reviewer notes, and supporting context are visible.' : 'Context is still light, but the packet can be reviewed.',
      icon: <Info className="size-4" aria-hidden="true" />,
      state: hasRecommendation || hasReviewerBrief ? ('complete' as const) : ('active' as const),
    },
    {
      title: 'Approver confirmed',
      detail: (actor || approval.approver_name) ? `Decision will be recorded under ${actor || approval.approver_name}.` : 'Add the final approver name before saving a decision.',
      icon: <UserRound className="size-4" aria-hidden="true" />,
      state: (actor || approval.approver_name) ? ('complete' as const) : ('active' as const),
    },
    {
      title: isClosed ? 'Decision saved' : 'Awaiting final decision',
      detail: isClosed
        ? `Packet closed as ${formatLabel(approval.status)}${approval.decided_at ? ` on ${approval.decided_at}` : ''}.`
        : 'Approve or deny to send this packet back into the workflow with an audit trail.',
      icon: isClosed ? <BadgeCheck className="size-4" aria-hidden="true" /> : <CircleDashed className="size-4" aria-hidden="true" />,
      state: isClosed ? ('complete' as const) : ('active' as const),
    },
  ]
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

function formatLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
