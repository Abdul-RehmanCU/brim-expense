import { Radar, RefreshCw, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import { listRiskScores, scanRisk, type RiskLevel, type RiskScanSummary, type RiskScoreItem } from '@/lib/api/backendClient'
import { useUiPreferences } from '@/lib/ui/preferences'

const severityClass: Record<RiskLevel, string> = {
  low: 'bg-slate-100 text-slate-700 dark:bg-slate-400/10 dark:text-slate-100',
  medium: 'bg-amber-100 text-amber-800 dark:bg-amber-400/10 dark:text-amber-100',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-400/10 dark:text-orange-100',
  critical: 'bg-red-100 text-red-800 dark:bg-red-400/10 dark:text-red-100',
}

export function RiskRadarPage() {
  const { locale, t } = useUiPreferences()
  const [scores, setScores] = useState<RiskScoreItem[]>([])
  const [summary, setSummary] = useState<RiskScanSummary | null>(null)
  const [minLevel, setMinLevel] = useState<RiskLevel>('medium')
  const [isLoading, setIsLoading] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loadScores(level = minLevel) {
    setIsLoading(true)
    setError(null)
    try {
      setScores(await listRiskScores({ min_level: level, limit: 100 }))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load risk scores.')
    } finally {
      setIsLoading(false)
    }
  }

  async function runScan() {
    setIsScanning(true)
    setError(null)
    try {
      const result = await scanRisk({ limit: 5000, reset_existing: true })
      setSummary(result)
      await loadScores(minLevel)
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : 'Could not run risk scan.')
    } finally {
      setIsScanning(false)
    }
  }

  useEffect(() => {
    let isActive = true

    listRiskScores({ min_level: minLevel, limit: 100 })
      .then((items) => {
        if (isActive) {
          setScores(items)
        }
      })
      .catch((loadError: unknown) => {
        if (isActive) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load risk scores.')
        }
      })

    return () => {
      isActive = false
    }
  }, [minLevel])

  return (
    <PageScaffold
      eyebrow={t('riskRadar.eyebrow')}
      title={t('riskRadar.title')}
      description={t('riskRadar.description')}
    >
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="surface-panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-border/70 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Radar className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{t('riskRadar.watchTitle')}</p>
                <p className="mt-1 text-sm text-muted-foreground">{t('riskRadar.watchBody')}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                className="h-9 rounded-lg border border-input bg-background px-2 text-sm text-foreground"
                value={minLevel}
                onChange={(event) => setMinLevel(event.target.value as RiskLevel)}
              >
                <option value="low">{t('riskRadar.filterLow')}</option>
                <option value="medium">{t('riskRadar.filterMedium')}</option>
                <option value="high">{t('riskRadar.filterHigh')}</option>
                <option value="critical">{t('riskRadar.filterCritical')}</option>
              </select>
              <Button type="button" variant="outline" onClick={() => void loadScores()} disabled={isLoading || isScanning}>
                <RefreshCw className="size-4" aria-hidden="true" />
                Refresh
              </Button>
              <Button type="button" onClick={runScan} disabled={isScanning}>
                <ShieldAlert className="size-4" aria-hidden="true" />
                {isScanning ? t('actions.scanning') : t('riskRadar.runScan')}
              </Button>
            </div>
          </div>

          {error ? <p className="m-4 rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">{error}</p> : null}
          {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('riskRadar.loading')}</p> : null}
          {!isLoading && scores.length === 0 ? <p className="p-4 text-sm text-muted-foreground">{t('riskRadar.noScores')}</p> : null}

          {scores.length > 0 ? (
            <div className="max-h-[38rem] overflow-auto">
              <table className="w-full min-w-[1100px] text-left text-sm">
                <thead className="table-head">
                  <tr>
                    <th className="px-4 py-3 font-medium">Employee</th>
                    <th className="px-4 py-3 font-medium">Department</th>
                    <th className="px-4 py-3 font-medium">Date</th>
                    <th className="px-4 py-3 font-medium">Merchant</th>
                    <th className="px-4 py-3 text-right font-medium">Amount</th>
                    <th className="px-4 py-3 font-medium">Level</th>
                    <th className="px-4 py-3 text-right font-medium">Score</th>
                    <th className="px-4 py-3 font-medium">Signals</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/70">
                  {scores.map((score) => (
                    <tr key={score.id ?? score.transaction_id} className="table-row">
                      <td className="px-4 py-3 text-muted-foreground">{score.employee ?? t('transactions.syntheticEmployee')}</td>
                      <td className="px-4 py-3 text-muted-foreground">{score.department ?? t('transactions.syntheticDepartment')}</td>
                      <td className="px-4 py-3 text-muted-foreground">{score.transaction_date ?? '-'}</td>
                      <td className="px-4 py-3 font-medium text-foreground">{score.merchant ?? '-'}</td>
                      <td className="px-4 py-3 text-right tabular-nums font-medium text-foreground">
                        {score.amount_cad.toLocaleString(locale, { style: 'currency', currency: 'CAD' })}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`status-chip ${severityClass[score.risk_level]}`}>{formatLabel(score.risk_level)}</span>
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{score.risk_score}</td>
                      <td className="max-w-xl px-4 py-3 text-muted-foreground">
                        <div className="flex flex-wrap gap-1.5">
                          {score.signals.map((signal) => (
                            <span key={`${score.transaction_id}-${signal.type}`} className={`status-chip ${severityClass[signal.severity]}`}>
                              {formatLabel(signal.type)}
                            </span>
                          ))}
                        </div>
                        <p className="mt-2 text-xs leading-5">{score.signals[0]?.message ?? 'No risk signals.'}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>

        <aside className="grid content-start gap-4">
          <MetricCard label="Scanned" value={summary?.total_scanned ?? 0} locale={locale} />
          <MetricCard label="Persisted" value={summary?.persisted ?? 0} locale={locale} />
          <MetricCard label="High or critical" value={summary?.high_or_critical ?? scores.filter((score) => score.risk_level === 'high' || score.risk_level === 'critical').length} locale={locale} />
          <section className="surface-panel p-4">
            <p className="text-sm font-semibold text-foreground">{t('riskRadar.whatFlagged')}</p>
            <div className="mt-3 space-y-2">
              {Object.entries(summary?.signal_counts ?? {}).length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('riskRadar.whatFlaggedEmpty')}</p>
              ) : null}
              {Object.entries(summary?.signal_counts ?? {}).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between gap-3 rounded-lg bg-muted px-3 py-2">
                  <span className="truncate text-sm text-muted-foreground">{formatLabel(type)}</span>
                  <span className="status-chip bg-background text-foreground">{count.toLocaleString(locale)}</span>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </PageScaffold>
  )
}

function MetricCard({ label, value, locale }: { label: string; value: number; locale: string }) {
  return (
    <div className="subtle-panel p-3">
      <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{value.toLocaleString(locale)}</p>
    </div>
  )
}

function formatLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
