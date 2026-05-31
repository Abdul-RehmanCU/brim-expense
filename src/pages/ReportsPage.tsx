import { ArrowUpRight, BarChart3, Building2, CalendarRange, ClipboardCheck, Download, FileSpreadsheet, LineChart as LineChartIcon, RefreshCw, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  generateExpenseReport,
  getReportScopeOptions,
  getExpenseReport,
  listExpenseReports,
  type ExpenseReportDetail,
  type ExpenseReportLineItem,
  type ReportGenerateResponse,
  type ReportScopeDepartmentOption,
  type ReportScopeEmployeeOption,
  type ReportVisualResult,
  type ExpenseReportSummary,
} from '@/lib/api/backendClient'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { useUiPreferences } from '@/lib/ui/preferences'

const chartPalette = ['#0f766e', '#f59e0b', '#2563eb', '#dc2626', '#8b5cf6', '#059669', '#ea580c']
const reportsPageSize = 20
const chartGridStroke = 'rgba(148,163,184,0.14)'
const chartCursorFill = 'rgba(15,118,110,0.05)'
const chartCursorStroke = 'rgba(15,118,110,0.18)'
const verticalBarRadius: [number, number, number, number] = [12, 12, 3, 3]
const horizontalBarRadius: [number, number, number, number] = [0, 12, 12, 0]
const customPeriodPreset = 'custom'

type ReportBuilderScope = 'employee' | 'department'
type ReportPeriodPreset = '30' | '60' | '90' | typeof customPeriodPreset

export function ReportsPage() {
  const [reports, setReports] = useState<ExpenseReportSummary[]>([])
  const [selectedReport, setSelectedReport] = useState<ExpenseReportDetail | null>(null)
  const [builderScope, setBuilderScope] = useState<ReportBuilderScope>('employee')
  const [employees, setEmployees] = useState<ReportScopeEmployeeOption[]>([])
  const [departments, setDepartments] = useState<ReportScopeDepartmentOption[]>([])
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')
  const [selectedDepartmentId, setSelectedDepartmentId] = useState('')
  const [periodPreset, setPeriodPreset] = useState<ReportPeriodPreset>('30')
  const [customDateStart, setCustomDateStart] = useState('')
  const [customDateEnd, setCustomDateEnd] = useState('')
  const [latestTransactionDate, setLatestTransactionDate] = useState<string | null>(null)
  const [isLoadingReports, setIsLoadingReports] = useState(true)
  const [isLoadingScopeOptions, setIsLoadingScopeOptions] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMoreReports, setHasMoreReports] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationResult, setGenerationResult] = useState<ReportGenerateResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const selectedReportRef = useRef<HTMLElement | null>(null)
  const { locale, t } = useUiPreferences()
  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: 'CAD',
      }),
    [locale],
  )
  const integerFormatter = useMemo(() => new Intl.NumberFormat(locale), [locale])
  const selectedEmployee = useMemo(
    () => employees.find((employee) => employee.id === selectedEmployeeId) ?? null,
    [employees, selectedEmployeeId],
  )
  const selectedDepartment = useMemo(
    () => departments.find((department) => department.id === selectedDepartmentId) ?? null,
    [departments, selectedDepartmentId],
  )
  const periodRange = useMemo(
    () => buildReportPeriodRange(periodPreset, customDateStart, customDateEnd, latestTransactionDate),
    [customDateEnd, customDateStart, latestTransactionDate, periodPreset],
  )
  const builderLabel = builderScope === 'employee' ? selectedEmployee?.full_name : selectedDepartment?.name
  const builderDepartmentHint = builderScope === 'employee' ? selectedEmployee?.department_name : null
  const generatedPlannerRequest = useMemo(
    () =>
      buildGeneratedReportRequest({
        builderScope,
        label: builderLabel,
        periodRange,
      }),
    [builderLabel, builderScope, periodRange],
  )
  const canGenerateReport =
    Boolean(builderLabel) && Boolean(periodRange.start && periodRange.end && generatedPlannerRequest.trim().length > 0)
  const generatedReports = useMemo(() => generationResult?.reports ?? [], [generationResult])
  const isRefreshing = isLoadingReports || isLoadingScopeOptions
  const teamSpendData = useMemo(() => buildTeamSpendData(generatedReports), [generatedReports])
  const teamFlagsData = useMemo(() => buildTeamFlagsData(generatedReports), [generatedReports])
  const categoryMixData = useMemo(() => buildCategoryMixData(selectedReport), [selectedReport])
  const monthlyTrendData = useMemo(() => buildMonthlyTrendData(selectedReport), [selectedReport])
  const policyMixData = useMemo(() => buildStatusMixData(selectedReport, 'policy'), [selectedReport])
  const riskMixData = useMemo(() => buildStatusMixData(selectedReport, 'risk'), [selectedReport])
  const lineItemGroups = useMemo(() => groupReportLineItems(selectedReport), [selectedReport])
  const requestedVisuals = useMemo(() => selectedReport?.visuals ?? [], [selectedReport])
  const showGeneratedOverview = teamSpendData.length > 0 && (generatedReports.length > 1 || requestedVisuals.length === 0)
  const hasScanCoverageWarning = Boolean(
    selectedReport && (selectedReport.policy_unscanned_count > 0 || selectedReport.risk_unscanned_count > 0),
  )
  const assistantContext = useMemo(
    () => ({
      routeId: 'reports' as const,
      title: 'Reports',
      summary: selectedReport
        ? `Looking at ${selectedReport.report_name ?? selectedReport.employee_name ?? 'the selected report'} with ${selectedReport.item_count} item(s).`
        : `Managing ${reports.length} saved report${reports.length === 1 ? '' : 's'}.`,
      focus: selectedReport
        ? {
            type: 'expense_report',
            id: selectedReport.id,
            label: selectedReport.report_name ?? selectedReport.employee_name ?? selectedReport.id,
            status: selectedReport.status,
          }
        : null,
      focusEntities: selectedReport
        ? [
            {
              type: 'expense_report',
              id: selectedReport.id,
              label: selectedReport.report_name ?? selectedReport.employee_name ?? selectedReport.id,
              status: selectedReport.status,
              attributes: {
                total_amount_cad: selectedReport.total_amount_cad,
                item_count: selectedReport.item_count,
                policy_flag_count: selectedReport.policy_flag_count,
                risk_flag_count: selectedReport.risk_flag_count,
              },
            },
          ]
        : [],
      visibleEntities: reports.slice(0, 8).map((report) => ({
        type: 'expense_report',
        id: report.id,
        label: report.report_name ?? report.employee_name ?? report.id,
        status: report.status,
        attributes: {
          total_amount_cad: report.total_amount_cad,
          item_count: report.item_count,
          policy_flag_count: report.policy_flag_count,
          risk_flag_count: report.risk_flag_count,
        },
      })),
      artifacts: selectedReport
        ? [
            {
              type: 'csv',
              id: `${selectedReport.id}:csv`,
              label: `${selectedReport.report_name ?? selectedReport.employee_name ?? 'Report'} CSV`,
              status: 'available',
              metadata: { report_id: selectedReport.id },
            },
            {
              type: 'brief',
              id: `${selectedReport.id}:brief`,
              label: `${selectedReport.report_name ?? selectedReport.employee_name ?? 'Report'} brief`,
              status: 'available',
              metadata: { report_id: selectedReport.id, visual_count: selectedReport.visuals.length },
            },
          ]
        : [],
      metrics: selectedReport
        ? {
            total_amount_cad: selectedReport.total_amount_cad,
            policy_flag_count: selectedReport.policy_flag_count,
            risk_flag_count: selectedReport.risk_flag_count,
          }
        : {
            report_count: reports.length,
          },
      availableViews: ['saved reports', 'selected report', 'generated visuals'],
      suggestions: [
        selectedReport ? `Summarize ${selectedReport.report_name ?? 'this report'}` : 'What reports have been generated?',
        'Generate a manager-ready brief.',
      ],
    }),
    [reports, selectedReport],
  )
  useAssistantPageContext(assistantContext)

  async function loadReports(selectReportId?: string) {
    setIsLoadingReports(true)
    setError(null)

    try {
      const response = await listExpenseReports({ limit: reportsPageSize })
      setReports(response.reports)
      setHasMoreReports(response.reports.length === reportsPageSize)

      const reportToSelect = selectReportId ?? selectedReport?.id
      if (reportToSelect) {
        setSelectedReport(await getExpenseReport(reportToSelect))
      } else {
        setSelectedReport(null)
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load reports.')
    } finally {
      setIsLoadingReports(false)
    }
  }

  async function loadScopeOptions() {
    setIsLoadingScopeOptions(true)
    setError(null)

    try {
      const scopeOptions = await getReportScopeOptions()
      setEmployees(scopeOptions.employees)
      setDepartments(scopeOptions.departments)
      setLatestTransactionDate(scopeOptions.latest_transaction_date)
      if (!selectedEmployeeId && scopeOptions.employees[0]) {
        setSelectedEmployeeId(scopeOptions.employees[0].id)
      }
      if (!selectedDepartmentId && scopeOptions.departments[0]) {
        setSelectedDepartmentId(scopeOptions.departments[0].id)
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load report options.')
    } finally {
      setIsLoadingScopeOptions(false)
    }
  }

  async function loadMoreReports() {
    setIsLoadingMore(true)
    setError(null)

    try {
      const response = await listExpenseReports({ limit: reportsPageSize, offset: reports.length })
      setReports((currentReports) => [...currentReports, ...response.reports])
      setHasMoreReports(response.reports.length === reportsPageSize)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load more reports.')
    } finally {
      setIsLoadingMore(false)
    }
  }

  async function generateDefaultReport() {
    if (!canGenerateReport) {
      return
    }

    setIsGenerating(true)
    setError(null)

    try {
      const report = await generateExpenseReport({
        request: generatedPlannerRequest,
        employee_id: builderScope === 'employee' ? selectedEmployeeId : undefined,
        employee_name: builderScope === 'employee' ? selectedEmployee?.full_name : undefined,
        department_id: builderScope === 'department' ? selectedDepartmentId : undefined,
        department_name: builderScope === 'department' ? selectedDepartment?.name : undefined,
        date_start: periodRange.start,
        date_end: periodRange.end,
        refresh_workflow: true,
      })
      setGenerationResult(report)
      setSelectedReport(report.reports[0] ?? null)
      await loadReports(report.reports[0]?.id)
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : 'Could not generate report.')
    } finally {
      setIsGenerating(false)
    }
  }

  function exportVisibleCsv() {
    if (!selectedReport) {
      return
    }

    const csv = buildVisibleReportCsv({
      generationResult,
      selectedReport,
      categoryMixData,
      monthlyTrendData,
      policyMixData,
      riskMixData,
    })
    const fileName = `${slugify(selectedReport.report_name ?? selectedReport.employee_name ?? 'report')}-report.csv`
    downloadCsv(csv, fileName)
  }

  function openApprovalFromReport(approvalRequestId: string) {
    window.history.pushState({}, '', `/approvals?approval=${encodeURIComponent(approvalRequestId)}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }

  useEffect(() => {
    let ignore = false

    async function loadInitialReports() {
      try {
        const response = await listExpenseReports({ limit: reportsPageSize })
        if (ignore) {
          return
        }

        setReports(response.reports)
        setHasMoreReports(response.reports.length === reportsPageSize)
      } catch (loadError) {
        if (!ignore) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load reports.')
        }
      } finally {
        if (!ignore) {
          setIsLoadingReports(false)
        }
      }
    }

    async function loadInitialScopeOptions() {
      try {
        const scopeOptions = await getReportScopeOptions()
        if (ignore) {
          return
        }

        setEmployees(scopeOptions.employees)
        setDepartments(scopeOptions.departments)
        setLatestTransactionDate(scopeOptions.latest_transaction_date)
        if (!selectedEmployeeId && scopeOptions.employees[0]) {
          setSelectedEmployeeId(scopeOptions.employees[0].id)
        }
        if (!selectedDepartmentId && scopeOptions.departments[0]) {
          setSelectedDepartmentId(scopeOptions.departments[0].id)
        }
      } catch (loadError) {
        if (!ignore) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load report options.')
        }
      } finally {
        if (!ignore) {
          setIsLoadingScopeOptions(false)
        }
      }
    }

    void loadInitialReports()
    void loadInitialScopeOptions()

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedReport || !selectedReportRef.current) {
      return
    }

    const frame = window.requestAnimationFrame(() => {
      selectedReportRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [selectedReport])

  async function openReport(reportId: string) {
    setError(null)

    try {
      setSelectedReport(await getExpenseReport(reportId))
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : 'Could not load report detail.')
    }
  }

  return (
    <PageScaffold
      eyebrow={t('reports.eyebrow')}
      title={t('reports.title')}
      description={t('reports.description')}
    >
      <section className="surface-panel p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileSpreadsheet className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{t('reports.startTitle')}</p>
                <p className="mt-1 text-sm text-muted-foreground">{t('reports.reportBody')}</p>
              </div>
            </div>
            <div className="mt-4 grid gap-4">
              <div className="flex flex-wrap gap-2">
                {([
                  { id: 'employee', label: 'Person', icon: UserRound },
                  { id: 'department', label: 'Team', icon: Building2 },
                ] as const).map((option) => {
                  const Icon = option.icon
                  const isActive = builderScope === option.id
                  return (
                    <button
                      key={option.id}
                      type="button"
                      className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
                        isActive
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-background text-muted-foreground hover:border-primary/25 hover:text-foreground'
                      }`}
                      onClick={() => setBuilderScope(option.id)}
                    >
                      <Icon className="size-4" aria-hidden="true" />
                      {option.label}
                    </button>
                  )
                })}
              </div>

              <div className="grid gap-3 md:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-foreground">{builderScope === 'employee' ? 'Person' : 'Team'}</span>
                  <select
                    className="h-10 rounded-lg border border-input bg-background px-3 text-sm text-foreground"
                    value={builderScope === 'employee' ? selectedEmployeeId : selectedDepartmentId}
                    onChange={(event) =>
                      builderScope === 'employee' ? setSelectedEmployeeId(event.target.value) : setSelectedDepartmentId(event.target.value)
                    }
                  >
                    <option value="">{builderScope === 'employee' ? 'Select a person' : 'Select a team'}</option>
                    {(builderScope === 'employee' ? employees : departments).map((option) => (
                      <option key={option.id} value={option.id}>
                        {'full_name' in option ? option.full_name : option.name}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="rounded-lg border border-border/70 bg-muted/35 p-3 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2 font-medium text-foreground">
                    <CalendarRange className="size-4" aria-hidden="true" />
                    Report package
                  </div>
                  <p className="mt-1 leading-5">
                    {builderLabel
                      ? `Generate a manager-ready packet for ${builderLabel}${builderDepartmentHint ? ` in ${builderDepartmentHint}` : ''} using grouped recent transactions, live policy checks, risk signals, and approval workflow state.`
                      : 'Choose a person or team to build a structured report package.'}
                  </p>
                </div>
              </div>

              <div className="grid gap-3">
                <div className="flex flex-wrap gap-2">
                  {([
                    { id: '30', label: 'Last 30 days' },
                    { id: '60', label: 'Last 60 days' },
                    { id: '90', label: 'Last 90 days' },
                    { id: customPeriodPreset, label: 'Custom range' },
                  ] as const).map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      className={`rounded-lg border px-3 py-2 text-sm transition ${
                        periodPreset === option.id
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-background text-muted-foreground hover:border-primary/25 hover:text-foreground'
                      }`}
                      onClick={() => setPeriodPreset(option.id)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {periodPreset === customPeriodPreset ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="grid gap-1 text-sm">
                      <span className="font-medium text-foreground">Start date</span>
                      <input
                        className="h-10 rounded-lg border border-input bg-background px-3 text-sm text-foreground"
                        type="date"
                        value={customDateStart}
                        onChange={(event) => setCustomDateStart(event.target.value)}
                      />
                    </label>
                    <label className="grid gap-1 text-sm">
                      <span className="font-medium text-foreground">End date</span>
                      <input
                        className="h-10 rounded-lg border border-input bg-background px-3 text-sm text-foreground"
                        type="date"
                        value={customDateEnd}
                        onChange={(event) => setCustomDateEnd(event.target.value)}
                      />
                    </label>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void loadReports()
                void loadScopeOptions()
              }}
              disabled={isRefreshing || isGenerating}
            >
              <RefreshCw className="size-4" aria-hidden="true" />
              {t('actions.refresh')}
            </Button>
            <Button type="button" onClick={generateDefaultReport} disabled={isGenerating || !canGenerateReport}>
              <Sparkles className="size-4" aria-hidden="true" />
              {isGenerating ? t('reports.generating') : t('reports.generate')}
            </Button>
          </div>
        </div>

        {error ? (
          <p className="mt-3 rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">
            {error}
          </p>
        ) : null}
        {generationResult ? (
          <div className="mt-3 rounded-lg border border-border/70 bg-muted/40 p-3 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">
              {t('reports.generatedSummary')
                .replace('{reports}', generationResult.generated_count.toLocaleString(locale))
                .replace('{reportsSuffix}', generationResult.generated_count === 1 ? '' : 's')
                .replace('{targets}', generationResult.targets.length.toLocaleString(locale))
                .replace('{targetsSuffix}', generationResult.targets.length === 1 ? '' : 's')}
            </p>
            <p className="mt-1">
              {t('reports.generatedPrepared').replace(
                '{targets}',
                generationResult.targets
                  .map((target) => (target.scope_type === 'department' ? `${target.resolved_label} team` : target.resolved_label))
                  .join(', '),
              )}
            </p>
          </div>
        ) : null}
      </section>

      <section className="grid gap-4">
        <aside className="surface-panel overflow-hidden">
          <div className="border-b border-border/70 p-4">
            <p className="text-sm font-semibold text-foreground">{t('reports.savedReportsTitle')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('reports.savedReportsBody')}</p>
          </div>
          {isLoadingReports ? <p className="p-4 text-sm text-muted-foreground">{t('reports.loadingReports')}</p> : null}
          {!isLoadingReports && reports.length === 0 ? <p className="p-4 text-sm text-muted-foreground">{t('reports.noReports')}</p> : null}
          <div className="desktop-scroll max-h-[22rem] space-y-2 overflow-y-auto p-3">
            {reports.map((report) => (
              <button
                key={report.id}
                type="button"
                className={`w-full rounded-2xl border px-4 py-3.5 text-left transition ${
                  selectedReport?.id === report.id
                    ? 'border-primary/25 bg-primary/8'
                    : 'border-border/70 bg-background hover:border-primary/20 hover:bg-muted/45'
                }`}
                onClick={() => void openReport(report.id)}
              >
                <span className="flex items-start justify-between gap-4">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-foreground">
                      {report.report_name ?? report.employee_name ?? t('reports.reportFallback')}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {report.department_name ?? 'Assigned department'} · {report.period_start} to {report.period_end}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-sm font-semibold tabular-nums text-foreground">
                      {currencyFormatter.format(report.total_amount_cad)}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">{report.item_count.toLocaleString(locale)} items</span>
                  </span>
                </span>
                <span className="mt-3 flex flex-wrap items-center gap-1.5">
                  <StatusPill value={report.workflow_status ?? report.status ?? 'draft'} />
                  <span className="status-chip bg-muted text-muted-foreground">
                    {report.policy_flag_count.toLocaleString(locale)} policy flags
                  </span>
                  <span className="status-chip bg-muted text-muted-foreground">
                    {report.risk_flag_count.toLocaleString(locale)} risk flags
                  </span>
                </span>
              </button>
            ))}
          </div>
          {hasMoreReports ? (
            <div className="border-t border-border/70 p-4">
              <Button type="button" variant="outline" onClick={() => void loadMoreReports()} disabled={isLoadingMore}>
                {isLoadingMore ? 'Loading more...' : 'Load more reports'}
              </Button>
            </div>
          ) : null}
        </aside>

        <section ref={selectedReportRef} className="surface-panel overflow-hidden scroll-mt-6">
          {!selectedReport ? (
            <p className="p-4 text-sm text-muted-foreground">{t('reports.reportSelectEmpty')}</p>
          ) : (
            <>
              <div className="border-b border-border/70 p-5">
                <p className="text-sm font-semibold text-foreground">Selected report</p>
                <p className="mt-1 text-sm text-muted-foreground">Review the generated packet, visuals, and included transactions in one place.</p>
              </div>
              <div className="flex flex-col gap-4 border-b border-border/70 p-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">
                    {selectedReport.report_name ?? selectedReport.employee_name ?? t('reports.reportFallback')}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {selectedReport.department_name ?? 'Assigned department'} · {selectedReport.period_start} to {selectedReport.period_end}
                  </p>
                  {selectedReport.grouping_reason ? (
                    <p className="mt-2 text-sm text-muted-foreground">{selectedReport.grouping_reason}</p>
                  ) : null}
                  {selectedReport.ai_summary ? <p className="mt-3 max-w-3xl text-sm text-muted-foreground">{selectedReport.ai_summary}</p> : null}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={exportVisibleCsv}>
                    <Download className="size-4" aria-hidden="true" />
                    Export to CSV
                  </Button>
                </div>
              </div>

              {hasScanCoverageWarning ? (
                <div className="border-b border-border/70 px-5 py-4">
                  <div className="rounded-lg border border-amber-300/70 bg-amber-100/70 p-3 text-sm text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-100">
                    {t('reports.incompleteCoverage')
                      .replace('{policy}', selectedReport.policy_unscanned_count.toLocaleString(locale))
                      .replace('{risk}', selectedReport.risk_unscanned_count.toLocaleString(locale))}
                  </div>
                </div>
              ) : null}

              <CfoReviewPanel report={selectedReport} integerFormatter={integerFormatter} onOpenApproval={openApprovalFromReport} />

              <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-3">
                <ReportMetric label={t('reports.total')} value={currencyFormatter.format(selectedReport.total_amount_cad)} />
                <ReportMetric label={t('reports.missingReceipts')} value={selectedReport.missing_receipt_count.toLocaleString(locale)} />
                <ReportMetric label={t('reports.missingPreapprovals')} value={selectedReport.missing_preapproval_count.toLocaleString(locale)} />
                <ReportMetric label={t('reports.openApprovals')} value={selectedReport.open_approval_count.toLocaleString(locale)} />
                <ReportMetric label={t('reports.policyFlags')} value={selectedReport.policy_flag_count.toLocaleString(locale)} />
                <ReportMetric label={t('reports.riskFlags')} value={selectedReport.risk_flag_count.toLocaleString(locale)} />
              </div>

              {requestedVisuals.length > 0 ? (
                <div className="grid gap-5 border-t border-border/70 p-5 lg:grid-cols-2">
                  {requestedVisuals.map((visual) => (
                    <ChartPanel
                      key={visual.id}
                      title={visual.title}
                      subtitle={visual.subtitle ?? 'Prepared from the selected report definition.'}
                      icon={<BarChart3 className="size-4" aria-hidden="true" />}
                      className={visual.chart_type === 'table' ? 'lg:col-span-2' : ''}
                    >
                      <ReportVisualRenderer visual={visual} currencyFormatter={currencyFormatter} integerFormatter={integerFormatter} locale={locale} />
                    </ChartPanel>
                  ))}
                </div>
              ) : null}

              {showGeneratedOverview ? (
                <div className="grid gap-5 border-t border-border/70 p-5 lg:grid-cols-2">
                  <ChartPanel
                    title={t('reports.generatedOverviewTitle')}
                    subtitle={t('reports.generatedOverviewBody')}
                    icon={<BarChart3 className="size-4" aria-hidden="true" />}
                  >
                    <ResponsiveContainer width="100%" height={320}>
                      <BarChart data={teamSpendData} margin={{ top: 12, right: 12, bottom: 2, left: -6 }} barCategoryGap="32%">
                        <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={chartGridStroke} />
                        <XAxis dataKey="employee" tickLine={false} axisLine={false} fontSize={11} interval={0} height={38} tickMargin={12} tickFormatter={truncateAxisLabel} />
                        <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={(value) => compactCurrency(value, locale)} />
                        <Tooltip content={<CurrencyTooltip formatter={currencyFormatter} totalValue={sumNumericValues(teamSpendData, 'total')} />} cursor={{ fill: chartCursorFill }} />
                        <Bar dataKey="total" radius={verticalBarRadius} maxBarSize={34} fill="#0f766e" activeBar={{ fill: '#115e59' }} />
                      </BarChart>
                    </ResponsiveContainer>
                  </ChartPanel>

                  <ChartPanel
                    title={t('reports.policyAndRiskPressure')}
                    subtitle={t('reports.policyAndRiskPressureBody')}
                    icon={<LineChartIcon className="size-4" aria-hidden="true" />}
                  >
                    <ResponsiveContainer width="100%" height={320}>
                      <BarChart data={teamFlagsData} margin={{ top: 12, right: 12, bottom: 2, left: -6 }} barCategoryGap="30%">
                        <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={chartGridStroke} />
                        <XAxis dataKey="employee" tickLine={false} axisLine={false} fontSize={11} interval={0} height={38} tickMargin={12} tickFormatter={truncateAxisLabel} />
                        <YAxis tickLine={false} axisLine={false} fontSize={12} />
                        <Tooltip content={<CountTooltip formatter={integerFormatter} totalValue={sumNumericValues(teamFlagsData, 'policyFlags') + sumNumericValues(teamFlagsData, 'riskFlags')} />} cursor={{ fill: 'rgba(37,99,235,0.05)' }} />
                        <Legend formatter={renderLegendLabel} />
                        <Bar dataKey="policyFlags" name={t('reports.policyFlags')} radius={verticalBarRadius} maxBarSize={26} fill="#f59e0b" activeBar={{ fill: '#d97706' }} />
                        <Bar dataKey="riskFlags" name={t('reports.riskFlags')} radius={verticalBarRadius} maxBarSize={26} fill="#2563eb" activeBar={{ fill: '#1d4ed8' }} />
                      </BarChart>
                    </ResponsiveContainer>
                  </ChartPanel>
                </div>
              ) : null}

              <div className="grid gap-5 border-t border-border/70 p-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                <ChartPanel
                  className="lg:row-span-2"
                  title={t('reports.categoryMix')}
                  subtitle={t('reports.categoryMixBody')}
                  icon={<BarChart3 className="size-4" aria-hidden="true" />}
                >
                  <ResponsiveContainer width="100%" height={360}>
                    <BarChart data={categoryMixData} layout="vertical" margin={{ top: 8, right: 12, bottom: 8, left: 0 }} barCategoryGap="28%">
                      <CartesianGrid strokeDasharray="4 8" horizontal={false} stroke={chartGridStroke} />
                      <XAxis type="number" tickLine={false} axisLine={false} fontSize={12} tickFormatter={(value) => compactCurrency(value, locale)} />
                      <YAxis type="category" dataKey="category" tickLine={false} axisLine={false} width={136} fontSize={12} tickFormatter={truncateAxisLabel} />
                      <Tooltip content={<CurrencyTooltip formatter={currencyFormatter} categoryKey="category" totalValue={selectedReport.total_amount_cad} />} cursor={{ fill: 'rgba(37,99,235,0.05)' }} />
                      <Bar dataKey="total" radius={horizontalBarRadius} barSize={18} fill="#2563eb" activeBar={{ fill: '#1d4ed8' }} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartPanel>

                <ChartPanel
                  title={t('reports.spendRhythm')}
                  subtitle={t('reports.spendRhythmBody')}
                  icon={<LineChartIcon className="size-4" aria-hidden="true" />}
                >
                  <ResponsiveContainer width="100%" height={280}>
                    <AreaChart data={monthlyTrendData} margin={{ top: 12, right: 12, bottom: 12, left: 0 }}>
                      <defs>
                        <linearGradient id="reportSpendGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#0f766e" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#0f766e" stopOpacity={0.04} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={chartGridStroke} />
                      <XAxis dataKey="month" tickLine={false} axisLine={false} fontSize={12} tickMargin={12} />
                      <YAxis tickLine={false} axisLine={false} fontSize={12} tickFormatter={(value) => compactCurrency(value, locale)} />
                      <Tooltip content={<CurrencyTooltip formatter={currencyFormatter} categoryKey="month" totalValue={sumNumericValues(monthlyTrendData, 'total')} />} cursor={{ stroke: chartCursorStroke, strokeWidth: 1 }} />
                      <Area type="monotone" dataKey="total" stroke="#0f766e" fill="url(#reportSpendGradient)" strokeWidth={2.5} activeDot={{ r: 5, fill: '#0f766e', strokeWidth: 0 }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartPanel>

                <ChartPanel
                  title="Review mix"
                  subtitle="Policy and risk states in the selected report."
                  icon={<FileSpreadsheet className="size-4" aria-hidden="true" />}
                >
                  <div className="grid h-full gap-3 md:grid-cols-2">
                    <MiniPieChart title="Policy" data={policyMixData} formatter={integerFormatter} />
                    <MiniPieChart title="Risk" data={riskMixData} formatter={integerFormatter} />
                  </div>
                </ChartPanel>
              </div>

              {selectedReport.policy_clauses.length > 0 ? (
                <div className="border-t border-border/70 p-5">
                  <div className="mb-3">
                    <p className="text-sm font-semibold text-foreground">Policy grounding</p>
                    <p className="mt-1 text-sm text-muted-foreground">Clauses attached to this report through rule citations and policy retrieval.</p>
                  </div>
                  <div className="grid gap-3">
                    {selectedReport.policy_clauses.map((clause) => (
                      <div key={`${clause.clause_id ?? clause.rule_code ?? clause.text.slice(0, 24)}`} className="subtle-panel p-4">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">{clause.title ?? clause.rule_code ?? 'Policy clause'}</span>
                          {clause.rule_code ? <StatusPill value={clause.rule_code.toLowerCase()} /> : null}
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">{clause.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="border-t border-border/70 p-5 pt-4">
                <div className="mb-3">
                  <p className="text-sm font-semibold text-foreground">Line items</p>
                  <p className="mt-1 text-sm text-muted-foreground">Normalized transactions included in the selected report.</p>
                </div>
                <div className="max-h-[32rem] overflow-auto rounded-lg border border-border/70">
                  <table className="w-full min-w-[1450px] text-left text-sm">
                    <thead className="table-head">
                      <tr>
                        <th className="px-4 py-3 font-medium">Date</th>
                        <th className="px-4 py-3 font-medium">Merchant</th>
                        <th className="px-4 py-3 font-medium">Category</th>
                        <th className="px-4 py-3 text-right font-medium">Amount</th>
                        <th className="px-4 py-3 font-medium">Receipt</th>
                        <th className="px-4 py-3 font-medium">Pre-approval</th>
                        <th className="px-4 py-3 font-medium">Approval</th>
                        <th className="px-4 py-3 font-medium">Recommendation</th>
                        <th className="px-4 py-3 font-medium">Policy</th>
                        <th className="px-4 py-3 font-medium">Risk</th>
                        <th className="px-4 py-3 font-medium">Next action</th>
                        <th className="px-4 py-3 font-medium">Purpose</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/70">
                      {lineItemGroups.map((group) => {
                        const item = group.representative
                        return (
                        <tr key={group.key} className="table-row">
                          <td className="px-4 py-3 text-muted-foreground">{item.transaction_date ?? '-'}</td>
                          <td className="px-4 py-3 font-medium text-foreground">
                            <div>{item.merchant ?? '-'}</div>
                            {group.items.length > 1 ? (
                              <div className="mt-1 text-xs font-normal text-primary">{group.items.length} linked rows in this review cluster</div>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">{item.category}</td>
                          <td className="px-4 py-3 text-right tabular-nums font-medium text-foreground">
                            {currencyFormatter.format(group.totalAmount)}
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill value={item.receipt_status ?? 'unknown'} />
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill value={item.preapproval_status ?? 'unknown'} />
                          </td>
                          <td className="px-4 py-3">
                            {item.approval_request_id ? (
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary transition hover:bg-primary/12"
                                onClick={() => openApprovalFromReport(item.approval_request_id!)}
                              >
                                <StatusPill value={item.approval_status ?? 'requested'} />
                                <ArrowUpRight className="size-3" aria-hidden="true" />
                                Open packet
                              </button>
                            ) : (
                              <StatusPill value={item.approval_status ?? 'not_requested'} />
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill value={item.approval_recommendation ?? 'none'} />
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill value={item.policy_status ?? 'compliant'} />
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill value={item.risk_level ?? 'low'} />
                          </td>
                          <td className="max-w-xs px-4 py-3 text-muted-foreground">{item.reviewer_next_action ?? '-'}</td>
                          <td className="px-4 py-3 text-muted-foreground">{item.business_purpose ?? '-'}</td>
                        </tr>
                      )})}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </section>
      </section>
    </PageScaffold>
  )
}

function buildReportPeriodRange(
  preset: ReportPeriodPreset,
  customStart: string,
  customEnd: string,
  latestTransactionDate: string | null,
): { start: string | null; end: string | null; label: string } {
  if (preset === customPeriodPreset) {
    const hasValidCustomRange = Boolean(customStart && customEnd && customStart <= customEnd)
    return {
      start: hasValidCustomRange ? customStart : null,
      end: hasValidCustomRange ? customEnd : null,
      label: hasValidCustomRange ? `${customStart} to ${customEnd}` : 'custom range',
    }
  }

  const end = latestTransactionDate ? new Date(`${latestTransactionDate}T12:00:00`) : new Date()
  const start = new Date()
  start.setTime(end.getTime())
  start.setDate(end.getDate() - (Number(preset) - 1))
  return {
    start: formatDateInputValue(start),
    end: formatDateInputValue(end),
    label: `last ${preset} days`,
  }
}

function buildGeneratedReportRequest({
  builderScope,
  label,
  periodRange,
}: {
  builderScope: ReportBuilderScope
  label: string | null | undefined
  periodRange: { start: string | null; end: string | null; label: string }
}) {
  if (!label || !periodRange.start || !periodRange.end) {
    return ''
  }

  const scopeLabel = builderScope === 'department' ? `${label} team` : label
  return [
    `Generate an intelligent expense report package for ${scopeLabel}.`,
    `Cover the period from ${periodRange.start} to ${periodRange.end}.`,
    'Use grouped recent transactions, real-time policy checks, risk signals, and approval workflow status.',
    'Include an executive summary, the most useful tables, clear approval blockers, notable policy pressure, and charts that explain spend and exceptions.',
  ].join(' ')
}

function formatDateInputValue(value: Date) {
  const localValue = new Date(value.getTime() - value.getTimezoneOffset() * 60000)
  return localValue.toISOString().slice(0, 10)
}

function ReportMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="subtle-panel p-3">
      <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  )
}

function CfoReviewPanel({
  onOpenApproval,
  report,
  integerFormatter,
}: {
  onOpenApproval: (approvalRequestId: string) => void
  report: ExpenseReportDetail
  integerFormatter: Intl.NumberFormat
}) {
  const approvalCounts = report.approval_recommendation_counts ?? {}
  const denyCount = approvalCounts.deny ?? 0
  const approveCount = approvalCounts.approve ?? 0
  const unknownCount = approvalCounts.unknown ?? 0
  const lineGroups = groupReportLineItems(report)
  const openApprovalItems = lineGroups.filter((group) => group.representative.approval_request_id && group.representative.approval_status === 'requested')
  const recommendedItems = lineGroups.filter((group) => group.representative.approval_recommendation)
  const headline = workflowHeadline(report.workflow_status)

  return (
    <div className="border-b border-border/70 p-5">
      <div className="subtle-panel overflow-hidden">
        <div className="flex flex-col gap-4 border-b border-border/70 p-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ClipboardCheck className="size-4" aria-hidden="true" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-foreground">CFO review packet</p>
                <StatusPill value={report.workflow_status} />
              </div>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{headline}</p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <MiniMetric label="Approve" value={integerFormatter.format(approveCount)} tone="good" />
            <MiniMetric label="Deny" value={integerFormatter.format(denyCount)} tone={denyCount > 0 ? 'bad' : 'neutral'} />
            <MiniMetric label="Unknown" value={integerFormatter.format(unknownCount)} tone="neutral" />
          </div>
        </div>

        <div className="grid gap-4 p-5 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Readiness checklist</p>
            <ChecklistRow label="Policy scans complete" ok={report.policy_unscanned_count === 0} detail={`${report.policy_unscanned_count} unscanned`} />
            <ChecklistRow label="Risk scans complete" ok={report.risk_unscanned_count === 0} detail={`${report.risk_unscanned_count} unscanned`} />
            <ChecklistRow label="Approval packets created" ok={openApprovalItems.length > 0 || report.open_approval_count === 0} detail={`${report.open_approval_count} open`} />
            <ChecklistRow label="Evidence blockers cleared" ok={report.missing_receipt_count + report.missing_preapproval_count === 0} detail={`${report.missing_receipt_count + report.missing_preapproval_count} missing`} />
          </div>

          <div>
            <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Approver next actions</p>
            {report.cfo_next_actions.length > 0 ? (
              <div className="mt-3 grid gap-2">
                {report.cfo_next_actions.slice(0, 4).map((action) => (
                  <div key={action} className="rounded-lg border border-border/70 bg-background/70 p-3 text-sm text-muted-foreground">
                    {action}
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-3 rounded-lg border border-border/70 bg-background/70 p-3 text-sm text-muted-foreground">
                No blocking next actions. The CFO can review the report totals and approve the clean packet.
              </p>
            )}
          </div>
        </div>

        {recommendedItems.length > 0 ? (
          <div className="border-t border-border/70 p-5">
            <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Line-level recommendations</p>
            <div className="mt-3 grid gap-3">
              {recommendedItems.slice(0, 5).map((group) => {
                const item = group.representative
                return (
                <div key={`${group.key}-recommendation`} className="rounded-lg border border-border/70 bg-background/70 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium text-foreground">
                      {item.merchant ?? 'Unknown merchant'}
                      {group.items.length > 1 ? <span className="ml-2 text-xs text-primary">{group.items.length} linked rows</span> : null}
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusPill value={item.approval_recommendation ?? 'unknown'} />
                      {item.approval_recommendation_confidence ? <StatusPill value={`${item.approval_recommendation_confidence}_confidence`} /> : null}
                    </div>
                  </div>
                  {item.approval_recommendation_rationale ? (
                    <p className="mt-2 text-sm text-muted-foreground">{item.approval_recommendation_rationale}</p>
                  ) : null}
                </div>
              )})}
            </div>
          </div>
        ) : null}

        {openApprovalItems.length > 0 ? (
          <div className="border-t border-border/70 p-5">
            <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">Open approval packets</p>
            <div className="mt-3 grid gap-2">
              {openApprovalItems.slice(0, 4).map((group) => {
                const item = group.representative
                return (
                <button
                  key={`${group.key}-approval-link`}
                  type="button"
                  className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-background/70 px-3 py-2 text-left transition hover:bg-muted/45"
                  onClick={() => item.approval_request_id && onOpenApproval(item.approval_request_id)}
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{item.merchant ?? 'Unknown merchant'}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {item.approval_request_id}
                      {group.items.length > 1 ? ` · ${group.items.length} linked rows` : ''}
                    </p>
                  </div>
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
                    Open approval
                    <ArrowUpRight className="size-3" aria-hidden="true" />
                  </span>
                </button>
              )})}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function MiniMetric({ label, value, tone }: { label: string; value: string; tone: 'good' | 'bad' | 'neutral' }) {
  const toneClass =
    tone === 'good'
      ? 'text-emerald-700 dark:text-emerald-100'
      : tone === 'bad'
        ? 'text-red-700 dark:text-red-100'
        : 'text-foreground'

  return (
    <div className="rounded-lg border border-border/70 bg-background/70 px-3 py-2">
      <p className={`text-lg font-semibold tabular-nums ${toneClass}`}>{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

function ChecklistRow({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-background/70 px-3 py-2 text-sm">
      <span className="text-foreground">{label}</span>
      <span className={ok ? 'text-emerald-700 dark:text-emerald-100' : 'text-amber-800 dark:text-amber-100'}>
        {ok ? 'Ready' : detail}
      </span>
    </div>
  )
}

function workflowHeadline(status: ExpenseReportDetail['workflow_status']) {
  if (status === 'ready_for_cfo') {
    return 'All selected transactions are scanned, clean, and packaged for final approval.'
  }
  if (status === 'pending_cfo_review') {
    return 'Approval packets have been created from the report line items and are waiting for one CFO decision per item.'
  }
  if (status === 'scan_incomplete') {
    return 'Some line items are missing policy or risk scan coverage. Regenerate with workflow refresh before relying on this report.'
  }
  return 'The report is grouped, but evidence or policy/risk issues need attention before final approval.'
}

function ChartPanel({
  title,
  subtitle,
  icon,
  children,
  className = '',
}: {
  title: string
  subtitle: string
  icon: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`subtle-panel overflow-hidden rounded-[22px] border border-border/70 bg-background/55 p-5 shadow-[0_18px_40px_-26px_rgba(15,23,42,0.65)] ${className}`}>
      <div className="mb-4 flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">{icon}</span>
        <div>
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        </div>
      </div>
      <div className="rounded-[18px] border border-border/60 bg-background/60 p-3 sm:p-4">{children}</div>
    </div>
  )
}

function MiniPieChart({
  data,
  formatter,
  title,
}: {
  data: Array<{ label: string; value: number }>
  formatter: Intl.NumberFormat
  title: string
}) {
  const safeData = data.length > 0 ? data : [{ label: 'none', value: 1 }]

  return (
    <div className="rounded-[18px] border border-border/70 bg-background/70 p-4">
      <div className="mb-1 flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{title}</p>
        <span className="text-xs text-muted-foreground">{formatter.format(data.reduce((sum, entry) => sum + entry.value, 0))} total</span>
      </div>
      <ResponsiveContainer width="100%" height={190}>
        <PieChart>
          <Tooltip content={<SimplePieTooltip formatter={formatter} totalValue={data.reduce((sum, entry) => sum + entry.value, 0)} />} />
          <Pie data={safeData} dataKey="value" nameKey="label" innerRadius={48} outerRadius={74} paddingAngle={2} stroke="rgba(15,23,42,0.08)" strokeWidth={1}>
            {safeData.map((entry, index) => (
              <Cell key={`${entry.label}-${index}`} fill={chartPalette[index % chartPalette.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="grid gap-2">
        {data.map((entry, index) => (
          <div key={entry.label} className="flex items-center justify-between gap-3 rounded-xl border border-border/50 bg-background/60 px-3 py-2 text-xs">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="size-2.5 rounded-full" style={{ backgroundColor: chartPalette[index % chartPalette.length] }} />
              {formatLabel(entry.label)}
            </span>
            <span className="font-medium text-foreground">{formatter.format(entry.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ReportVisualRenderer({
  visual,
  currencyFormatter,
  integerFormatter,
  locale,
}: {
  visual: ReportVisualResult
  currencyFormatter: Intl.NumberFormat
  integerFormatter: Intl.NumberFormat
  locale: string
}) {
  const primarySeries = visual.series[0]
  const primaryKey = primarySeries?.key ?? visual.metric
  const dataKey = `values.${primaryKey}`
  const isCurrencyMetric = visual.metric === 'sum_amount_cad'
  const formatter = isCurrencyMetric ? currencyFormatter : integerFormatter
  const totalValue = visual.rows.reduce((sum, row) => sum + (row.values[primaryKey] ?? 0), 0)

  if (visual.chart_type === 'table') {
    return (
      <div className="overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full min-w-[420px] text-left text-sm">
          <thead className="table-head">
            <tr>
              <th className="px-4 py-3 font-medium">Label</th>
              <th className="px-4 py-3 text-right font-medium">{primarySeries?.label ?? formatLabel(visual.metric)}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/70">
            {visual.rows.map((row) => (
              <tr key={row.label} className="table-row">
                <td className="px-4 py-3 text-foreground">{row.label}</td>
                <td className="px-4 py-3 text-right tabular-nums text-foreground">
                  {formatter.format(row.values[primaryKey] ?? 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (visual.chart_type === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Tooltip content={<VisualTooltip formatter={formatter} totalValue={totalValue} />} />
          <Pie data={visual.rows} dataKey={dataKey} nameKey="label" innerRadius={56} outerRadius={92} paddingAngle={2} stroke="rgba(15,23,42,0.08)" strokeWidth={1}>
            {visual.rows.map((row, index) => (
              <Cell key={`${row.label}-${index}`} fill={chartPalette[index % chartPalette.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (visual.chart_type === 'line') {
    return (
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={visual.rows} margin={{ top: 12, right: 12, bottom: 12, left: 0 }}>
          <defs>
            <linearGradient id={`visualGradient-${visual.id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0f766e" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#0f766e" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={chartGridStroke} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} tickMargin={12} />
          <YAxis
            tickLine={false}
            axisLine={false}
            fontSize={12}
            tickFormatter={(value) => (isCurrencyMetric ? compactCurrency(value, locale) : integerFormatter.format(value))}
          />
          <Tooltip content={<VisualTooltip formatter={formatter} totalValue={totalValue} />} cursor={{ stroke: chartCursorStroke, strokeWidth: 1 }} />
          <Area type="monotone" dataKey={dataKey} stroke="#0f766e" fill={`url(#visualGradient-${visual.id})`} strokeWidth={2.5} activeDot={{ r: 5, fill: '#0f766e', strokeWidth: 0 }} />
        </AreaChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={visual.rows} margin={{ top: 12, right: 12, bottom: 2, left: -6 }} barCategoryGap="30%">
        <CartesianGrid strokeDasharray="4 8" vertical={false} stroke={chartGridStroke} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={11} interval={0} height={38} tickMargin={12} tickFormatter={truncateAxisLabel} />
        <YAxis
          tickLine={false}
          axisLine={false}
          fontSize={12}
          tickFormatter={(value) => (isCurrencyMetric ? compactCurrency(value, locale) : integerFormatter.format(value))}
        />
        <Tooltip content={<VisualTooltip formatter={formatter} totalValue={totalValue} />} cursor={{ fill: chartCursorFill }} />
        <Bar dataKey={dataKey} radius={verticalBarRadius} maxBarSize={34} fill="#0f766e" activeBar={{ fill: '#115e59' }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function StatusPill({ value }: { value: string }) {
  const className =
    value === 'critical' || value === 'policy_violation'
      ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
      : value === 'denied' || value === 'rejected' || value === 'deny'
        ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
      : value === 'high' || value === 'approval_evidence_needed'
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
        : value === 'missing' || value === 'requested' || value === 'pending_cfo_review' || value === 'action_required' || value === 'scan_incomplete'
          ? 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
        : value === 'medium' || value === 'context_needed' || value === 'review_required'
          ? 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'
          : value === 'approved' || value === 'submitted' || value === 'scanned' || value === 'approve' || value === 'ready_for_cfo'
            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-100'
          : 'bg-muted text-muted-foreground'

  return <span className={`status-chip ${className}`}>{formatLabel(value)}</span>
}

function formatLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function buildTeamSpendData(reports: ExpenseReportDetail[]) {
  return reports
    .map((report) => ({
      employee: report.report_name ?? report.employee_name ?? 'Unknown',
      total: report.total_amount_cad,
      items: report.item_count,
    }))
    .sort((left, right) => right.total - left.total)
}

function buildTeamFlagsData(reports: ExpenseReportDetail[]) {
  return reports
    .map((report) => ({
      employee: report.report_name ?? report.employee_name ?? 'Unknown',
      policyFlags: report.policy_flag_count,
      riskFlags: report.risk_flag_count,
    }))
    .sort((left, right) => right.policyFlags + right.riskFlags - (left.policyFlags + left.riskFlags))
}

function buildCategoryMixData(report: ExpenseReportDetail | null) {
  if (!report) {
    return []
  }

  const totals = new Map<string, number>()
  for (const item of report.line_items) {
    totals.set(item.category, (totals.get(item.category) ?? 0) + item.amount_cad)
  }

  return [...totals.entries()]
    .map(([category, total]) => ({ category, total: Number(total.toFixed(2)) }))
    .sort((left, right) => right.total - left.total)
    .slice(0, 8)
}

function buildMonthlyTrendData(report: ExpenseReportDetail | null) {
  if (!report) {
    return []
  }

  const totals = new Map<string, number>()
  for (const item of report.line_items) {
    const month = item.transaction_date?.slice(0, 7) ?? 'Unknown'
    totals.set(month, (totals.get(month) ?? 0) + item.amount_cad)
  }

  return [...totals.entries()]
    .map(([month, total]) => ({ month, total: Number(total.toFixed(2)) }))
    .sort((left, right) => left.month.localeCompare(right.month))
}

function buildStatusMixData(report: ExpenseReportDetail | null, type: 'policy' | 'risk') {
  if (!report) {
    return []
  }

  const counts = new Map<string, number>()
  for (const item of report.line_items) {
    const key = type === 'policy' ? item.policy_status ?? 'compliant' : item.risk_level ?? 'low'
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }

  return [...counts.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((left, right) => right.value - left.value)
}

type ReportLineGroup = {
  key: string
  items: ExpenseReportLineItem[]
  representative: ExpenseReportLineItem
  totalAmount: number
}

function groupReportLineItems(report: ExpenseReportDetail | null): ReportLineGroup[] {
  if (!report) {
    return []
  }

  const groups = new Map<string, ExpenseReportLineItem[]>()
  for (const item of report.line_items) {
    const key = item.review_group_key ?? fallbackReportGroupKey(item)
    groups.set(key, [...(groups.get(key) ?? []), item])
  }

  return Array.from(groups.entries()).map(([key, items]) => {
    const sortedItems = [...items].sort((left, right) => (left.transaction_date ?? '').localeCompare(right.transaction_date ?? '') || left.id.localeCompare(right.id))
    const representative = sortedItems[0]

    return {
      key,
      items: sortedItems,
      representative,
      totalAmount: Number(
        (representative.review_group_total_amount_cad || sortedItems.reduce((total, item) => total + item.amount_cad, 0)).toFixed(2),
      ),
    }
  })
}

function fallbackReportGroupKey(item: ExpenseReportLineItem) {
  if (!item.merchant || !item.transaction_date) {
    return `transaction:${item.transaction_id}`
  }

  return [
    'review-context',
    normalizeGroupValue(item.merchant),
    item.transaction_date,
    normalizeGroupValue(item.category),
  ].join('|')
}

function normalizeGroupValue(value: string | null | undefined) {
  return (value ?? 'unknown').trim().toLowerCase().replace(/\s+/g, ' ')
}

function buildVisibleReportCsv({
  generationResult,
  selectedReport,
  categoryMixData,
  monthlyTrendData,
  policyMixData,
  riskMixData,
}: {
  generationResult: ReportGenerateResponse | null
  selectedReport: ExpenseReportDetail
  categoryMixData: Array<{ category: string; total: number }>
  monthlyTrendData: Array<{ month: string; total: number }>
  policyMixData: Array<{ label: string; value: number }>
  riskMixData: Array<{ label: string; value: number }>
}) {
  const rows: string[][] = []
  const pushRow = (...values: Array<string | number | null | undefined>) => {
    rows.push(values.map((value) => String(value ?? '')))
  }

  pushRow('Visible Report Export')
  pushRow('Report Name', selectedReport.report_name)
  pushRow('Employee', selectedReport.employee_name)
  pushRow('Department', selectedReport.department_name)
  pushRow('Period', `${selectedReport.period_start} to ${selectedReport.period_end}`)
  pushRow('Total CAD', selectedReport.total_amount_cad.toFixed(2))
  pushRow('Missing receipts', selectedReport.missing_receipt_count)
  pushRow('Missing pre-approvals', selectedReport.missing_preapproval_count)
  pushRow('Open approvals', selectedReport.open_approval_count)
  pushRow('Policy flags', selectedReport.policy_flag_count)
  pushRow('Risk flags', selectedReport.risk_flag_count)
  pushRow('Policy unscanned', selectedReport.policy_unscanned_count)
  pushRow('Risk unscanned', selectedReport.risk_unscanned_count)
  pushRow('Approval ready', selectedReport.approval_ready ? 'yes' : 'no')
  pushRow('Workflow status', selectedReport.workflow_status)
  pushRow('Blocker count', selectedReport.blocker_count)
  pushRow('Approval recommendations', JSON.stringify(selectedReport.approval_recommendation_counts))
  pushRow('CFO next actions', selectedReport.cfo_next_actions.join('; '))
  pushRow('Grouping reason', selectedReport.grouping_reason)

  if (generationResult) {
    pushRow()
    pushRow('Generated Request', generationResult.request)
    pushRow('Planner Source', generationResult.planner_source)
    pushRow('Generated Count', generationResult.generated_count)
    pushRow('SQL Preview', generationResult.sql_preview)
    pushRow()
    pushRow('Generated Reports')
    pushRow('Report Name', 'Employee', 'Department', 'Total CAD', 'Items', 'Missing Pre-approvals', 'Policy Flags', 'Risk Flags')
    for (const report of generationResult.reports) {
      pushRow(
        report.report_name,
        report.employee_name,
        report.department_name,
        report.total_amount_cad.toFixed(2),
        report.item_count,
        report.missing_preapproval_count,
        report.policy_flag_count,
        report.risk_flag_count,
      )
    }
  }

  pushRow()
  pushRow('Category Mix')
  pushRow('Category', 'Total CAD')
  for (const row of categoryMixData) {
    pushRow(row.category, row.total.toFixed(2))
  }

  pushRow()
  pushRow('Monthly Trend')
  pushRow('Month', 'Total CAD')
  for (const row of monthlyTrendData) {
    pushRow(row.month, row.total.toFixed(2))
  }

  pushRow()
  pushRow('Policy Mix')
  pushRow('Status', 'Count')
  for (const row of policyMixData) {
    pushRow(row.label, row.value)
  }

  pushRow()
  pushRow('Risk Mix')
  pushRow('Level', 'Count')
  for (const row of riskMixData) {
    pushRow(row.label, row.value)
  }

  if (selectedReport.policy_clauses.length > 0) {
    pushRow()
    pushRow('Policy Clauses')
    pushRow('Rule Code', 'Title', 'Text')
    for (const clause of selectedReport.policy_clauses) {
      pushRow(clause.rule_code, clause.title, clause.text)
    }
  }

  pushRow()
  pushRow('Line Items')
  pushRow(
    'Date',
    'Merchant',
    'Category',
    'Amount CAD',
    'Receipt Status',
    'Pre-approval Status',
    'Approval Status',
    'Policy Status',
    'Risk Level',
    'Approval Request ID',
    'Approval Recommendation',
    'Approval Rationale',
    'Reviewer Next Action',
    'Business Purpose',
    'Guest Names',
    'Transaction ID',
  )
  for (const item of selectedReport.line_items) {
    pushRow(
      item.transaction_date,
      item.merchant,
      item.category,
      item.amount_cad.toFixed(2),
      item.receipt_status,
      item.preapproval_status,
      item.approval_status,
      item.policy_status,
      item.risk_level,
      item.approval_request_id,
      item.approval_recommendation,
      item.approval_recommendation_rationale,
      item.reviewer_next_action,
      item.business_purpose,
      item.guest_names.join('; '),
      item.transaction_id,
    )
  }

  return rows
    .map((row) => row.map(escapeCsvCell).join(','))
    .join('\n')
}

function escapeCsvCell(value: string) {
  if (/[",\n]/.test(value)) {
    return `"${value.replaceAll('"', '""')}"`
  }
  return value
}

function downloadCsv(csv: string, fileName: string) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function compactCurrency(value: number, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'CAD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function renderLegendLabel(value: string) {
  return <span className="text-xs text-muted-foreground">{value}</span>
}

function sumNumericValues<T extends Record<string, unknown>>(rows: T[], key: keyof T) {
  return rows.reduce((sum, row) => sum + Number(row[key] ?? 0), 0)
}

function truncateAxisLabel(value: string) {
  return value.length > 14 ? `${value.slice(0, 12)}...` : value
}

function CurrencyTooltip({
  active,
  formatter,
  label,
  payload,
  categoryKey,
  totalValue,
}: {
  active?: boolean
  formatter: Intl.NumberFormat
  label?: string
  payload?: Array<{ color?: string; name?: string; value?: number; payload?: Record<string, unknown> }>
  categoryKey?: string
  totalValue?: number
}) {
  if (!active || !payload?.length) {
    return null
  }

  const title =
    categoryKey && payload[0]?.payload?.[categoryKey]
      ? String(payload[0].payload?.[categoryKey])
      : label

  return (
    <div className="chart-tooltip">
      {title ? <p className="font-medium text-foreground">{title}</p> : null}
      {payload.map((entry) => (
        <div key={entry.name} className="chart-tooltip-row">
          <span className="chart-tooltip-label">
            <span className="chart-tooltip-swatch" style={{ backgroundColor: entry.color ?? '#0f766e' }} />
            {entry.name ?? 'Total'}
          </span>
          <span className="font-medium text-foreground">{formatter.format(Number(entry.value ?? 0))}</span>
        </div>
      ))}
      {typeof totalValue === 'number' && totalValue > 0 ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Share: {((Number(payload[0]?.value ?? 0) / totalValue) * 100).toFixed(1)}% of visible total
        </p>
      ) : null}
    </div>
  )
}

function CountTooltip({
  active,
  formatter,
  label,
  payload,
  totalValue,
}: {
  active?: boolean
  formatter: Intl.NumberFormat
  label?: string
  payload?: Array<{ name?: string; value?: number }>
  totalValue?: number
}) {
  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="chart-tooltip">
      {label ? <p className="font-medium text-foreground">{label}</p> : null}
      {payload.map((entry) => (
        <div key={entry.name} className="chart-tooltip-row">
          <span className="chart-tooltip-label">
            <span className="chart-tooltip-swatch bg-muted-foreground/40" />
            {entry.name}
          </span>
          <span className="font-medium text-foreground">{formatter.format(Number(entry.value ?? 0))}</span>
        </div>
      ))}
      {typeof totalValue === 'number' && totalValue > 0 ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Combined share: {((payload.reduce((sum, entry) => sum + Number(entry.value ?? 0), 0) / totalValue) * 100).toFixed(1)}%
        </p>
      ) : null}
    </div>
  )
}

function SimplePieTooltip({
  active,
  formatter,
  payload,
  totalValue,
}: {
  active?: boolean
  formatter: Intl.NumberFormat
  payload?: Array<{ name?: string; value?: number }>
  totalValue?: number
}) {
  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="chart-tooltip">
      <p className="font-medium text-foreground">{formatLabel(String(payload[0].name ?? 'Value'))}</p>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-label">Count</span>
        <span className="font-medium text-foreground">{formatter.format(Number(payload[0].value ?? 0))}</span>
      </div>
      {typeof totalValue === 'number' && totalValue > 0 ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Share: {((Number(payload[0].value ?? 0) / totalValue) * 100).toFixed(1)}%
        </p>
      ) : null}
    </div>
  )
}

function VisualTooltip({
  active,
  formatter,
  label,
  payload,
  totalValue,
}: {
  active?: boolean
  formatter: Intl.NumberFormat
  label?: string
  payload?: Array<{ color?: string; name?: string; value?: number }>
  totalValue?: number
}) {
  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="chart-tooltip">
      {label ? <p className="font-medium text-foreground">{label}</p> : null}
      {payload.map((entry) => (
        <div key={entry.name} className="chart-tooltip-row">
          <span className="chart-tooltip-label">
            <span className="chart-tooltip-swatch" style={{ backgroundColor: entry.color ?? '#0f766e' }} />
            {entry.name ?? 'Value'}
          </span>
          <span className="font-medium text-foreground">{formatter.format(Number(entry.value ?? 0))}</span>
        </div>
      ))}
      {typeof totalValue === 'number' && totalValue > 0 ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          Share: {((Number(payload[0]?.value ?? 0) / totalValue) * 100).toFixed(1)}% of visible values
        </p>
      ) : null}
    </div>
  )
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}
