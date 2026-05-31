import { AlertTriangle, Download, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  resetTransactions as resetTransactionsRequest,
  type TransactionResetResponse,
} from '@/lib/api/backendClient'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { downloadTextFile } from '@/lib/insights/artifacts'
import { listRecentTransactions, type TransactionListItem } from '@/lib/supabase/transactions'
import { useUiPreferences } from '@/lib/ui/preferences'

const transactionsPageSize = 50

export function TransactionsPage() {
  const [transactions, setTransactions] = useState<TransactionListItem[]>([])
  const [resetSummary, setResetSummary] = useState<TransactionResetResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMoreTransactions, setHasMoreTransactions] = useState(false)
  const [isResetting, setIsResetting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { locale, t } = useUiPreferences()
  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: 'CAD',
      }),
    [locale],
  )
  const assistantContext = useMemo(
    () => {
      const visibleTransactionIds = transactions.map((transaction) => transaction.id)
      const visibleTotalAmount = transactions.reduce((total, transaction) => total + transaction.amountCad, 0)
      const visibleDepartments = [...new Set(transactions.map((transaction) => transaction.departmentName).filter(Boolean))]
      const topVisibleItems = [...transactions]
        .sort((left, right) => right.amountCad - left.amountCad)
        .slice(0, 10)
        .map((transaction) => ({
          transaction_id: transaction.id,
          merchant: transaction.normalizedMerchantName ?? transaction.merchantName ?? transaction.id,
          amount_cad: transaction.amountCad,
          business_category: transaction.businessCategory,
          employee: transaction.employeeName,
          department: transaction.departmentName,
          transaction_date: transaction.transactionDate,
        }))

      return {
        routeId: 'transactions' as const,
        title: 'Transactions',
        summary: `Viewing ${transactions.length} recent transactions.`,
        filters: {
          visible_transaction_ids: visibleTransactionIds,
        },
        details: {
          quick_summary: 'This table shows recent expense transactions with merchant, category, employee, department, amount, country, and source fingerprint.',
          visible_rows: transactions.slice(0, 12).map((transaction) => ({
            transaction_id: transaction.id,
            merchant: transaction.normalizedMerchantName ?? transaction.merchantName ?? transaction.id,
            amount_cad: transaction.amountCad,
            business_category: transaction.businessCategory,
            employee: transaction.employeeName,
            department: transaction.departmentName,
            transaction_date: transaction.transactionDate,
            merchant_country: transaction.merchantCountry,
          })),
          top_items: topVisibleItems,
        },
        focus: transactions[0]
          ? {
              type: 'transaction_row',
              id: transactions[0].id,
              label: transactions[0].normalizedMerchantName ?? transactions[0].merchantName ?? transactions[0].id,
              status: transactions[0].businessCategory,
            }
          : null,
        focusEntities: transactions[0]
          ? [
              {
                type: 'transaction_row',
                id: transactions[0].id,
                label: transactions[0].normalizedMerchantName ?? transactions[0].merchantName ?? transactions[0].id,
                status: transactions[0].businessCategory,
                attributes: {
                  amount_cad: transactions[0].amountCad,
                  department: transactions[0].departmentName,
                  employee: transactions[0].employeeName,
                },
              },
            ]
          : [],
        visibleEntities: transactions.slice(0, 12).map((transaction) => ({
          type: 'transaction_row',
          id: transaction.id,
          label: transaction.normalizedMerchantName ?? transaction.merchantName ?? transaction.id,
          status: transaction.businessCategory,
          attributes: {
            amount_cad: transaction.amountCad,
            department: transaction.departmentName,
            employee: transaction.employeeName,
            transaction_date: transaction.transactionDate,
          },
        })),
        metrics: {
          visible_count: transactions.length,
          visible_total_amount_cad: Number(visibleTotalAmount.toFixed(2)),
          visible_department_count: visibleDepartments.length,
        },
        availableViews: ['recent transactions', 'top visible items', 'merchant and category table'],
        suggestions: [
          'Show the top 10 most expensive visible transactions as a chart.',
          'Summarize spend by category from this table.',
        ],
      }
    },
    [transactions],
  )
  useAssistantPageContext(assistantContext)

  async function loadTransactions() {
    setIsLoading(true)
    setError(null)

    try {
      const loadedTransactions = await listRecentTransactions({ limit: transactionsPageSize })
      setTransactions(loadedTransactions)
      setHasMoreTransactions(loadedTransactions.length === transactionsPageSize)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load transactions.')
    } finally {
      setIsLoading(false)
    }
  }

  async function loadMoreTransactions() {
    setIsLoadingMore(true)
    setError(null)

    try {
      const loadedTransactions = await listRecentTransactions({
        limit: transactionsPageSize,
        offset: transactions.length,
      })
      setTransactions((currentTransactions) => [...currentTransactions, ...loadedTransactions])
      setHasMoreTransactions(loadedTransactions.length === transactionsPageSize)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load more transactions.')
    } finally {
      setIsLoadingMore(false)
    }
  }

  async function resetTransactions() {
    const confirmed = window.confirm(t('transactions.confirmReset'))
    if (!confirmed) {
      return
    }

    setIsResetting(true)
    setError(null)

    try {
      const summary = await resetTransactionsRequest()
      setResetSummary(summary)
      await loadTransactions()
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : 'Could not clear transactions.')
    } finally {
      setIsResetting(false)
    }
  }

  function downloadTransactions() {
    if (transactions.length === 0) {
      return
    }

    const header = [
      t('transactions.date'),
      t('transactions.merchant'),
      t('transactions.category'),
      t('transactions.employee'),
      t('transactions.department'),
      t('transactions.amountCad'),
      t('transactions.country'),
      t('transactions.mcc'),
      t('transactions.fingerprint'),
    ]
    const rows = transactions.map((transaction) => [
      transaction.transactionDate ?? '',
      transaction.normalizedMerchantName ?? transaction.merchantName ?? '',
      transaction.businessCategory ?? '',
      transaction.employeeName ?? t('transactions.syntheticEmployee'),
      transaction.departmentName ?? t('transactions.syntheticDepartment'),
      transaction.amountCad.toFixed(2),
      transaction.merchantCountry ?? '',
      transaction.merchantCategoryCode ?? '',
      transaction.sourceFingerprint ?? '',
    ])
    const csv = [header, ...rows]
      .map((row) =>
        row
          .map((value) => (/[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value))
          .join(','),
      )
      .join('\n')

    downloadTextFile(csv, `transactions-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8')
  }

  useEffect(() => {
    let ignore = false

    listRecentTransactions({ limit: transactionsPageSize })
      .then((loadedTransactions) => {
        if (!ignore) {
          setTransactions(loadedTransactions)
          setHasMoreTransactions(loadedTransactions.length === transactionsPageSize)
        }
      })
      .catch((loadError: unknown) => {
        if (!ignore) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load transactions.')
        }
      })
      .finally(() => {
        if (!ignore) {
          setIsLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [])

  return (
    <PageScaffold
      eyebrow={t('transactions.eyebrow')}
      title={t('transactions.title')}
      description={t('transactions.description')}
    >
      <section className="surface-panel overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border/70 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">{t('transactions.recent')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('transactions.recentBody')}</p>
          </div>
          <Button type="button" variant="outline" onClick={downloadTransactions} disabled={transactions.length === 0 || isLoading}>
            <Download className="size-4" aria-hidden="true" />
            {t('transactions.download')}
          </Button>
        </div>

        {error ? <p className="m-4 rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">{error}</p> : null}
        {resetSummary ? (
          <p className="m-4 rounded-lg border border-amber-300/70 bg-amber-100/70 p-3 text-sm text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-100">
            {t('transactions.clearSummary')
              .replace('{transactions}', resetSummary.deleted_transactions.toLocaleString(locale))
              .replace('{raw}', resetSummary.deleted_raw_transactions.toLocaleString(locale))
              .replace('{receipts}', resetSummary.deleted_receipts.toLocaleString(locale))
              .replace('{preapprovals}', resetSummary.deleted_preapprovals.toLocaleString(locale))
              .replace('{remainder}', formatResetRemainder(resetSummary, locale, t))}
          </p>
        ) : null}
        {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('transactions.loading')}</p> : null}

        {!isLoading && transactions.length === 0 && !error ? (
          <p className="p-4 text-sm text-muted-foreground">{t('transactions.noTransactions')}</p>
        ) : null}

        {transactions.length > 0 ? (
          <>
            <div className="max-h-[38rem] overflow-auto">
              <table className="w-full min-w-[1100px] text-left text-sm">
              <thead className="table-head">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('transactions.date')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.merchant')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.category')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.employee')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.department')}</th>
                  <th className="px-4 py-3 text-right font-medium">{t('transactions.amountCad')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.country')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.mcc')}</th>
                  <th className="px-4 py-3 font-medium">{t('transactions.fingerprint')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/70">
                {transactions.map((transaction) => (
                  <tr key={transaction.id} className="table-row">
                    <td className="px-4 py-3 text-muted-foreground">{transaction.transactionDate ?? '-'}</td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground">{transaction.normalizedMerchantName ?? transaction.merchantName}</p>
                      <p className="mt-1 max-w-72 truncate text-xs text-muted-foreground">{transaction.description}</p>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {transaction.businessCategory}
                      <span className="ml-2 text-xs text-muted-foreground">
                        {Math.round(transaction.categoryConfidence * 100)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{transaction.employeeName ?? t('transactions.syntheticEmployee')}</td>
                    <td className="px-4 py-3 text-muted-foreground">{transaction.departmentName ?? t('transactions.syntheticDepartment')}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium text-foreground">
                      {currencyFormatter.format(transaction.amountCad)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{transaction.merchantCountry ?? '-'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{transaction.merchantCategoryCode ?? '-'}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{transaction.sourceFingerprint ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
            {hasMoreTransactions ? (
              <div className="border-t border-border/70 p-4">
                <Button type="button" variant="outline" onClick={() => void loadMoreTransactions()} disabled={isLoadingMore}>
                  {isLoadingMore ? 'Loading more...' : 'Load more transactions'}
                </Button>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      <section className="surface-panel p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <AlertTriangle className="size-4 text-destructive" aria-hidden="true" />
              {t('transactions.clearDataTitle')}
            </div>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              {t('transactions.clearDataBody')}
            </p>
          </div>
          <Button
            type="button"
            variant="destructive"
            onClick={resetTransactions}
            disabled={isLoading || isResetting}
          >
            <Trash2 className="size-4" aria-hidden="true" />
            {isResetting ? t('transactions.clearing') : t('transactions.clearImport')}
          </Button>
        </div>
      </section>
    </PageScaffold>
  )
}

function formatResetRemainder(
  summary: TransactionResetResponse,
  locale: string,
  t: ReturnType<typeof useUiPreferences>['t'],
) {
  return [
    `${summary.deleted_policy_checks.toLocaleString(locale)} ${t('transactions.resetPolicyChecks')}`,
    `${summary.deleted_violations.toLocaleString(locale)} ${t('transactions.resetViolations')}`,
    `${summary.deleted_risk_scores.toLocaleString(locale)} ${t('transactions.resetRiskScores')}`,
    `${summary.deleted_approval_requests.toLocaleString(locale)} ${t('transactions.resetApprovalRequests')}`,
    `${summary.deleted_expense_report_items.toLocaleString(locale)} ${t('transactions.resetReportItems')}`,
    `${summary.deleted_expense_reports.toLocaleString(locale)} ${t('transactions.resetEmptyReports')}`,
  ].join(', ')
}
