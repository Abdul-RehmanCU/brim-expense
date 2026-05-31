import { ArrowRight, Bot, FileCheck2, ListChecks, ShieldCheck, Sparkles, Upload } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { PolyAvatar } from '@/components/assistant/PolyAvatar'
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
  const [sceneVisible, setSceneVisible] = useState(false)
  const [textVisible, setTextVisible] = useState(false)
  const { locale, t } = useUiPreferences()
  const workflowSectionRef = useRef<HTMLElement | null>(null)
  const assistantContext = useMemo(
    () => ({
      routeId: 'dashboard' as const,
      title: 'Overview',
      summary: summary
        ? `PolyPilot overview. Backend is ${backendStatus} with ${summary.normalized_transaction_count.toLocaleString(locale)} imported transactions, ${summary.employee_count} mapped employees, and ${summary.department_count} departments.`
        : `PolyPilot overview. Backend is ${backendStatus}.`,
      focusEntities: summary
        ? [
            {
              type: 'workspace_overview',
              label: 'PolyPilot overview',
              status: backendStatus,
              attributes: {
                normalized_transaction_count: summary.normalized_transaction_count,
                employee_count: summary.employee_count,
                department_count: summary.department_count,
              },
            },
          ]
        : [],
      visibleEntities: summary
        ? [
            {
              type: 'summary_metric',
              label: 'Imported transactions',
              attributes: { value: summary.normalized_transaction_count },
            },
            {
              type: 'summary_metric',
              label: 'Mapped employees',
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
            backend_status: backendStatus,
            normalized_rows: summary.normalized_transaction_count,
            employee_count: summary.employee_count,
            department_count: summary.department_count,
          }
        : {
            backend_status: backendStatus,
          },
      availableViews: ['overview', 'workspace signals', 'workflow'],
      suggestions: [
        'What can PolyPilot help me do from here?',
        'Summarize the current workspace signals.',
      ],
    }),
    [backendStatus, locale, summary],
  )
  useAssistantPageContext(assistantContext)

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
        }
      }
    }

    void loadInitialBackendStatus()

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    const workflowSection = workflowSectionRef.current
    const scrollContainer = workflowSection?.closest('.desktop-scroll')
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (scrollContainer instanceof HTMLElement) {
      scrollContainer.scrollTop = 0
    }

    if (prefersReducedMotion) {
      setSceneVisible(true)
      setTextVisible(true)
      return
    }

    let interrupted = false
    const timeoutIds = [
      window.setTimeout(() => setSceneVisible(true), 120),
      window.setTimeout(() => setTextVisible(true), 980),
      window.setTimeout(() => {
        if (!interrupted) {
          workflowSection?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      }, 3600),
    ]

    const markInterrupted = () => {
      interrupted = true
    }

    scrollContainer?.addEventListener('wheel', markInterrupted, { passive: true })
    scrollContainer?.addEventListener('touchstart', markInterrupted, { passive: true })
    scrollContainer?.addEventListener('pointerdown', markInterrupted, { passive: true })

    return () => {
      interrupted = true
      for (const timeoutId of timeoutIds) {
        window.clearTimeout(timeoutId)
      }
      scrollContainer?.removeEventListener('wheel', markInterrupted)
      scrollContainer?.removeEventListener('touchstart', markInterrupted)
      scrollContainer?.removeEventListener('pointerdown', markInterrupted)
    }
  }, [])

  return (
    <PageScaffold
      eyebrow={t('dashboard.eyebrow')}
      title={t('dashboard.title')}
      description={t('dashboard.description')}
    >
      <section className="surface-panel relative overflow-hidden p-0">
        <div className={`absolute inset-0 transition-opacity duration-[1400ms] ${sceneVisible ? 'opacity-100' : 'opacity-0'}`}>
          <DashboardScene3D />
        </div>
        <div
          className={`pointer-events-none absolute inset-0 transition-opacity duration-[1400ms] ${
            sceneVisible ? 'opacity-100' : 'opacity-0'
          } bg-[radial-gradient(circle_at_16%_26%,rgba(116,231,212,0.18),transparent_24%),radial-gradient(circle_at_82%_18%,rgba(255,208,122,0.14),transparent_22%),linear-gradient(90deg,rgba(6,15,24,0.92)_0%,rgba(6,15,24,0.8)_34%,rgba(6,15,24,0.36)_62%,rgba(6,15,24,0.12)_100%)]`}
        />
        <div
          className={`pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),transparent_24%,transparent_76%,rgba(6,15,24,0.28)_100%)] transition-opacity duration-[1600ms] ${
            sceneVisible ? 'opacity-100' : 'opacity-0'
          }`}
        />

        <div className="relative z-10 flex min-h-[36rem] flex-col justify-between px-5 py-5 sm:px-6 lg:min-h-[40rem] lg:px-8 lg:py-7">
          <div
            className={`flex flex-wrap items-start justify-between gap-4 transition-all duration-700 ${
              textVisible ? 'translate-y-0 opacity-100' : 'translate-y-6 opacity-0'
            }`}
            style={{ transitionDelay: textVisible ? '120ms' : '0ms' }}
          >
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary backdrop-blur">
                <Sparkles className="size-3.5" aria-hidden="true" />
                {t('dashboard.heroBadge')}
              </span>
              <StatusPill status={backendStatus} />
            </div>

            <div className="flex flex-wrap justify-end gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              <SceneTag>{t('routes.import.label')}</SceneTag>
              <SceneTag>{t('routes.policyRules.label')}</SceneTag>
              <SceneTag>{t('routes.compliance.label')}</SceneTag>
              <SceneTag>{t('routes.reports.label')}</SceneTag>
            </div>
          </div>

          <div className="max-w-xl py-8 sm:py-10">
            <div
              className={`flex items-start gap-4 transition-all duration-700 ${
                textVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
              }`}
              style={{ transitionDelay: textVisible ? '260ms' : '0ms' }}
            >
              <PolyAvatar className="mt-1 size-14 shrink-0 rounded-[24px] ring-1 ring-white/12 sm:size-16" />
              <div className="min-w-0">
                <h1 className="max-w-xl text-4xl font-semibold text-foreground sm:text-5xl">
                  {t('dashboard.heroTitle')}
                </h1>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
                  {t('dashboard.heroDescription')}
                </p>
              </div>
            </div>

            <div
              className={`mt-7 space-y-4 transition-all duration-700 ${
                textVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
              }`}
              style={{ transitionDelay: textVisible ? '460ms' : '0ms' }}
            >
              <IntroLine icon={Upload} label={t('dashboard.introImportLabel')} body={t('dashboard.introImportBody')} />
              <IntroLine icon={ShieldCheck} label={t('dashboard.introReviewLabel')} body={t('dashboard.introReviewBody')} />
              <IntroLine icon={Bot} label={t('dashboard.introAskLabel')} body={t('dashboard.introAskBody')} />
            </div>

            <div
              className={`mt-7 flex flex-wrap gap-2 transition-all duration-700 ${
                textVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
              }`}
              style={{ transitionDelay: textVisible ? '640ms' : '0ms' }}
            >
              <Button asChild size="lg">
                <a href="/import">
                  <Upload className="size-4" aria-hidden="true" />
                  {t('dashboard.primaryAction')}
                </a>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href="/talk-to-data">
                  <Bot className="size-4" aria-hidden="true" />
                  {t('dashboard.secondaryAction')}
                </a>
              </Button>
            </div>
          </div>

          <div
            className={`flex justify-end transition-all duration-700 ${
              textVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
            }`}
            style={{ transitionDelay: textVisible ? '780ms' : '0ms' }}
          >
            <div className="max-w-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{t('dashboard.sceneLabel')}</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{t('dashboard.sceneBody')}</p>
            </div>
          </div>
        </div>
      </section>

      <section ref={workflowSectionRef} className="surface-panel p-5">
        <div>
          <p className="text-sm font-semibold text-foreground">{t('dashboard.workflowTitle')}</p>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{t('dashboard.workflowBody')}</p>
        </div>

        <div className="mt-5 space-y-4">
          <WorkflowRow
            href="/import"
            icon={Upload}
            step="01"
            label={t('dashboard.workflowImportLabel')}
            body={t('dashboard.workflowImportBody')}
          />
          <WorkflowRow
            href="/compliance"
            icon={FileCheck2}
            step="02"
            label={t('dashboard.workflowReviewLabel')}
            body={t('dashboard.workflowReviewBody')}
          />
          <WorkflowRow
            href="/approvals"
            icon={ListChecks}
            step="03"
            label={t('dashboard.workflowApproveLabel')}
            body={t('dashboard.workflowApproveBody')}
          />
          <WorkflowRow
            href="/reports"
            icon={ArrowRight}
            step="04"
            label={t('dashboard.workflowReportLabel')}
            body={t('dashboard.workflowReportBody')}
          />
        </div>
      </section>
    </PageScaffold>
  )
}

function StatusPill({ status }: { status: 'checking' | 'online' | 'offline' }) {
  const { t } = useUiPreferences()
  const label =
    status === 'online'
      ? t('dashboard.signalConnectionOnline')
      : status === 'offline'
        ? t('dashboard.signalConnectionOffline')
        : t('dashboard.signalConnectionChecking')

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
      <span
        className={`size-2 rounded-full ${
          status === 'online'
            ? 'bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,0.14)]'
            : status === 'offline'
              ? 'bg-amber-400 shadow-[0_0_0_4px_rgba(251,191,36,0.14)]'
              : 'bg-sky-300 shadow-[0_0_0_4px_rgba(125,211,252,0.14)]'
        }`}
      />
      {label}
    </span>
  )
}

function SceneTag({ children }: { children: string }) {
  return <span className="rounded-full border border-white/10 bg-card/72 px-3 py-1 backdrop-blur">{children}</span>
}

function IntroLine({ body, icon: Icon, label }: { body: string; icon: LucideIcon; label: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
    </div>
  )
}

function WorkflowRow({
  body,
  href,
  icon: Icon,
  label,
  step,
}: {
  body: string
  href: string
  icon: LucideIcon
  label: string
  step: string
}) {
  return (
    <a
      href={href}
      className="flex items-start gap-4 rounded-xl border border-border/70 px-4 py-3 transition-colors hover:bg-muted/40"
    >
      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{step}</span>
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
      <ArrowRight className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    </a>
  )
}
