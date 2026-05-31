import { Suspense, lazy, useCallback, useEffect, useMemo, useState, type ComponentType } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { ImportPage } from '@/pages/ImportPage'
import { TalkToDataPage } from '@/pages/TalkToDataPage'
import { getRouteByPath, routes, type AppRouteId } from '@/routes/routes'

const TransactionsPage = lazy(() => import('@/pages/TransactionsPage').then((module) => ({ default: module.TransactionsPage })))
const CompliancePage = lazy(() => import('@/pages/CompliancePage').then((module) => ({ default: module.CompliancePage })))
const ApprovalsPage = lazy(() => import('@/pages/ApprovalsPage').then((module) => ({ default: module.ApprovalsPage })))
const ReportsPage = lazy(() => import('@/pages/ReportsPage').then((module) => ({ default: module.ReportsPage })))
const PolicyRulesPage = lazy(() => import('@/pages/PolicyRulesPage').then((module) => ({ default: module.PolicyRulesPage })))

const pageByRoute: Record<AppRouteId, ComponentType> = {
  dashboard: DashboardPage,
  import: ImportPage,
  talkToData: TalkToDataPage,
  transactions: TransactionsPage,
  compliance: CompliancePage,
  approvals: ApprovalsPage,
  reports: ReportsPage,
  policyRules: PolicyRulesPage,
}

function getCurrentPath() {
  return window.location.pathname === '/' ? routes[0].path : window.location.pathname
}

function App() {
  const [path, setPath] = useState(getCurrentPath)

  useEffect(() => {
    const handlePopState = () => setPath(getCurrentPath())

    window.addEventListener('popstate', handlePopState)

    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const activeRoute = useMemo(() => getRouteByPath(path), [path])
  const ActivePage = pageByRoute[activeRoute.id]

  const handleNavigate = useCallback((nextPath: string) => {
    window.history.pushState({}, '', nextPath)
    setPath(nextPath)
  }, [])

  return (
    <AppShell activeRouteId={activeRoute.id} onNavigate={handleNavigate}>
      <Suspense fallback={<PageLoadingFallback label={activeRoute.label} />}>
        <ActivePage />
      </Suspense>
    </AppShell>
  )
}

function PageLoadingFallback({ label }: { label: string }) {
  return (
    <div className="grid gap-5">
      <section className="subtle-panel overflow-hidden p-6">
        <div className="flex items-center gap-3">
          <span className="size-3 animate-pulse rounded-full bg-primary" />
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">Loading {label}</p>
        </div>
        <div className="mt-6 grid gap-3">
          <div className="h-8 w-56 animate-pulse rounded-2xl bg-muted" />
          <div className="h-4 w-full max-w-2xl animate-pulse rounded-full bg-muted" />
          <div className="h-4 w-full max-w-xl animate-pulse rounded-full bg-muted" />
        </div>
      </section>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="h-28 animate-pulse rounded-3xl border border-border/70 bg-muted/50" />
        <div className="h-28 animate-pulse rounded-3xl border border-border/70 bg-muted/50" />
        <div className="h-28 animate-pulse rounded-3xl border border-border/70 bg-muted/50" />
      </div>
    </div>
  )
}

export default App
