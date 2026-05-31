import { ArrowUpRight, RefreshCw, Server, ShieldCheck, Target, Waves } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { DashboardScene3D } from '@/components/dashboard/DashboardScene3D'
import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  getBackendHealth,
  getBackendTransactionsSummary,
  type BackendTransactionsSummary,
} from '@/lib/api/backendClient'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { useUiPreferences } from '@/lib/ui/preferences'

export function DashboardPage() {
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [summary, setSummary] = useState<BackendTransactionsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { locale, t } = useUiPreferences()
  const assistantContext = useMemo(
    () => ({
      routeId: 'dashboard' as const,
      title: 'Overview',
      summary: summary
        ? `Backend is ${backendStatus}. There are ${summary.normalized_transaction_count.toLocaleString(locale)} normalized transactions across ${summary.department_count} departments.`
        : `Backend is ${backendStatus}.`,
      focusEntities: summary
        ? [
            {
              type: 'workspace_overview',
              label: 'System overview',
              status: backendStatus,
              attributes: {
                normalized_transaction_count: summary.normalized_transaction_count,
                department_count: summary.department_count,
              },
            },
          ]
        : [],
      visibleEntities: summary
        ? [
            {
              type: 'summary_metric',
              label: 'Raw rows',
              attributes: { value: summary.raw_transaction_count },
            },
            {
              type: 'summary_metric',
              label: 'Normalized transactions',
              attributes: { value: summary.normalized_transaction_count },
            },
            {
              type: 'summary_metric',
              label: 'Employees',
              attributes: { value: summary.employee_count },
            },
            {
              type: 'summary_metric',
              label: 'Departments',
              attributes: { value: summary.department_count },
            },
          ]
        : [],
      metrics: summary
        ? {
            raw_rows: summary.raw_transaction_count,
            normalized_rows: summary.normalized_transaction_count,
            employee_count: summary.employee_count,
            department_count: summary.department_count,
          }
        : {
            backend_status: backendStatus,
          },
      availableViews: ['system status', 'coverage summary', 'overview'],
      suggestions: [
        'Summarize the current system status.',
        'What should I review first?',
      ],
    }),
    [backendStatus, locale, summary],
  )
  useAssistantPageContext(assistantContext)

  async function loadBackendStatus() {
    setBackendStatus('checking')
    setError(null)

    try {
      await getBackendHealth()
      setSummary(await getBackendTransactionsSummary())
      setBackendStatus('online')
    } catch (loadError) {
      setSummary(null)
      setBackendStatus('offline')
      setError(loadError instanceof Error ? loadError.message : 'Backend is not reachable.')
    }
  }

  useEffect(() => {
    let ignore = false

    async function loadInitialBackendStatus() {
      try {
        await getBackendHealth()
        const loadedSummary = await getBackendTransactionsSummary()

        if (!ignore) {
          setSummary(loadedSummary)
          setBackendStatus('online')
        }
      } catch (loadError) {
        if (!ignore) {
          setSummary(null)
          setBackendStatus('offline')
          setError(loadError instanceof Error ? loadError.message : 'Backend is not reachable.')
        }
      }
    }

    void loadInitialBackendStatus()

    return () => {
      ignore = true
    }
  }, [])

  return (
    <PageScaffold
      eyebrow={t('dashboard.eyebrow')}
      title={t('dashboard.title')}
      description={t('dashboard.description')}
    >
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.02fr)_minmax(300px,0.98fr)]">
        <div className="surface-panel relative overflow-hidden p-5">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(86,242,215,0.22),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(255,208,122,0.14),transparent_30%)]" />
          <div className="relative">
            <div>
              <p className="text-sm font-semibold text-foreground">{t('dashboard.heroTitle')}</p>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{t('dashboard.heroDescription')}</p>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <SignalCard
                icon={Waves}
                label={t('dashboard.heroSignalOne')}
                value={
                  backendStatus === 'online'
                    ? `${summary?.normalized_transaction_count.toLocaleString(locale) ?? 0}`
                    : t('dashboard.heroSignalPending')
                }
              />
              <SignalCard
                icon={ShieldCheck}
                label={t('dashboard.heroSignalTwo')}
                value={summary ? `${summary.employee_count}/${summary.department_count}` : t('dashboard.heroSignalPending')}
              />
              <SignalCard icon={Target} label={t('dashboard.heroSignalThree')} value={t('dashboard.heroSignalThreeValue')} />
            </div>
          </div>
        </div>

        <div className="surface-panel relative overflow-hidden p-4 xl:p-5">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(116,231,212,0.16),transparent_45%),linear-gradient(180deg,rgba(255,255,255,0.06),transparent)]" />
          <div className="relative h-full">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{t('dashboard.sceneLabel')}</p>
                <p className="mt-1 text-sm text-muted-foreground">{t('dashboard.sceneBody')}</p>
              </div>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/6 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
                <ArrowUpRight className="size-3.5 text-primary" aria-hidden="true" />
                {t('dashboard.sceneBadge')}
              </span>
            </div>

            <div className="relative overflow-hidden rounded-[1.5rem] border border-white/10 bg-[radial-gradient(circle_at_20%_20%,rgba(111,217,255,0.18),transparent_20%),radial-gradient(circle_at_75%_70%,rgba(255,208,122,0.14),transparent_24%),linear-gradient(180deg,rgba(255,255,255,0.07),rgba(5,14,22,0.42))] xl:max-h-[29rem]">
              <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.045)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:32px_32px] opacity-35" />
              <DashboardScene3D />

              <div className="pointer-events-none absolute left-4 top-4 rounded-2xl border border-white/12 bg-card/85 px-3 py-2 shadow-lg backdrop-blur">
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  {t('dashboard.overlayOneLabel')}
                </p>
                <p className="mt-1 text-sm font-semibold text-foreground">{t('dashboard.overlayOneValue')}</p>
              </div>

              <div className="pointer-events-none absolute bottom-4 left-4 rounded-2xl border border-white/12 bg-card/85 px-3 py-2 shadow-lg backdrop-blur">
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  {t('dashboard.overlayTwoLabel')}
                </p>
                <p className="mt-1 text-sm font-semibold text-foreground">{t('dashboard.overlayTwoValue')}</p>
              </div>

              <div className="pointer-events-none absolute right-4 top-[4.5rem] rounded-2xl border border-white/12 bg-card/85 px-3 py-2 shadow-lg backdrop-blur">
                <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  {t('dashboard.overlayThreeLabel')}
                </p>
                <p className="mt-1 text-sm font-semibold text-foreground">{t('dashboard.overlayThreeValue')}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.12fr)_minmax(320px,0.88fr)]">
        <div className="surface-panel p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Server className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{t('dashboard.backendBoundary')}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {backendStatus === 'checking'
                    ? t('dashboard.backendChecking')
                    : backendStatus === 'online'
                      ? t('dashboard.backendOnline')
                      : t('dashboard.backendOffline')}
                </p>
              </div>
            </div>
            <Button type="button" variant="outline" onClick={loadBackendStatus} disabled={backendStatus === 'checking'}>
              <RefreshCw className="size-4" aria-hidden="true" />
              {t('actions.refresh')}
            </Button>
          </div>

          {error ? <p className="mt-3 rounded-lg border border-amber-300/70 bg-amber-100/70 p-3 text-sm text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-100">{error}</p> : null}

          {summary ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <SummaryMetric label={t('dashboard.rawRows')} value={summary.raw_transaction_count} locale={locale} />
              <SummaryMetric label={t('dashboard.normalizedCount')} value={summary.normalized_transaction_count} locale={locale} />
              <SummaryMetric label={t('dashboard.employeeCount')} value={summary.employee_count} locale={locale} />
              <SummaryMetric label={t('dashboard.departmentCount')} value={summary.department_count} locale={locale} />
            </div>
          ) : null}
        </div>

        <div className="surface-panel relative overflow-hidden p-4">
          <div className="pointer-events-none absolute inset-x-10 top-2 h-20 rounded-full bg-primary/12 blur-3xl" />
          <div className="relative grid gap-3">
            <InsightPanel
              icon={ShieldCheck}
              label={t('scaffold.currentMilestone')}
              body={t('scaffold.currentMilestoneBody')}
            />
            <InsightPanel
              icon={ShieldCheck}
              label={t('scaffold.dataSource')}
              body={t('scaffold.dataSourceBody')}
            />
            <InsightPanel icon={Target} label={t('scaffold.aiBoundary')} body={t('scaffold.aiBoundaryBody')} />
          </div>
        </div>
      </section>
    </PageScaffold>
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

function SignalCard({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/12 bg-white/6 p-3 shadow-[0_20px_45px_-34px_rgba(0,0,0,0.55)] backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary/12 text-primary">
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      </div>
      <p className="mt-3 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  )
}

function InsightPanel({ body, icon: Icon, label }: { body: string; icon: LucideIcon; label: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4 shadow-[0_24px_50px_-40px_rgba(0,0,0,0.65)] backdrop-blur">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary">
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold text-foreground">{label}</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{body}</p>
        </div>
      </div>
    </div>
  )
}
