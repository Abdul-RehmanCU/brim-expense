import { CheckCircle2, Database, Upload } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  importTransactions,
  validateTransactionDataQuality,
  type DataQualityValidationResponse,
  type TransactionImportRequest,
  type TransactionImportResponse,
} from '@/lib/api/backendClient'
import { parseTransactionCsv, type ParseImportResult } from '@/lib/import/csvParser'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { listSyntheticAssignmentEmployees } from '@/lib/supabase/transactions'
import { useUiPreferences } from '@/lib/ui/preferences'

function readFileAsText(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()

    reader.addEventListener('load', () => resolve(String(reader.result ?? '')))
    reader.addEventListener('error', () => reject(new Error('Could not read the selected file.')))
    reader.readAsText(file)
  })
}

export function ImportPage() {
  const [csvText, setCsvText] = useState('')
  const [sourceFileName, setSourceFileName] = useState<string | null>(null)
  const [parseResult, setParseResult] = useState<ParseImportResult | null>(null)
  const [validationResult, setValidationResult] = useState<DataQualityValidationResponse | null>(null)
  const [importResult, setImportResult] = useState<TransactionImportResponse | null>(null)
  const [isWorking, setIsWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { locale, t } = useUiPreferences()

  const canImport = useMemo(
    () => Boolean(parseResult && parseResult.rows.length > 0 && parseResult.missingColumns.length === 0),
    [parseResult],
  )
  const currencyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: 'CAD',
      }),
    [locale],
  )
  const previewRows = parseResult?.rows.slice(0, 8) ?? []
  const assistantContext = useMemo(
    () => ({
      routeId: 'import' as const,
      title: 'Import',
      summary: parseResult
        ? `Prepared ${parseResult.rows.length} rows with ${parseResult.errors.length} row error(s).`
        : sourceFileName
          ? `Working with ${sourceFileName}.`
          : 'Add a CSV to prepare the import.',
      visibleEntities: previewRows.map((row, index) => ({
        type: 'import_preview_row',
        id: `${sourceFileName ?? 'preview'}-${index}`,
        label: row.transaction.normalizedMerchantName ?? row.transaction.merchantName ?? `Row ${index + 1}`,
        status: row.transaction.businessCategory,
        attributes: {
          amount_cad: row.transaction.amountCad,
          employee_id: row.transaction.employeeId,
          department_id: row.transaction.departmentId,
        },
      })),
      artifacts: sourceFileName
        ? [
            {
              type: 'csv_upload',
              id: sourceFileName,
              label: sourceFileName,
              status: canImport ? 'ready' : 'draft',
              metadata: {
                preview_rows: parseResult?.rows.length ?? 0,
              },
            },
          ]
        : [],
      metrics: {
        rows_ready: parseResult?.rows.length ?? 0,
        row_errors: parseResult?.errors.length ?? 0,
        missing_columns: parseResult?.missingColumns.length ?? 0,
        backend_findings: validationResult?.summary.finding_count ?? 0,
        inserted_count: importResult?.inserted_count ?? 0,
      },
      availableViews: ['csv preview', 'import readiness', 'import results'],
      suggestions: [
        'What is blocking this import?',
        'Summarize the import readiness.',
      ],
    }),
    [canImport, importResult?.inserted_count, parseResult, previewRows, sourceFileName, validationResult?.summary.finding_count],
  )
  useAssistantPageContext(assistantContext)

  function serializeRowsForBackend(rows: NonNullable<ParseImportResult['rows']>): TransactionImportRequest['rows'] {
    return rows.map((row) => ({
      source_row_number: row.sourceRowNumber,
      source_fingerprint: row.sourceFingerprint,
      raw_payload: row.rawPayload as Record<string, unknown>,
      transaction: {
        source_row_number: row.sourceRowNumber,
        source_fingerprint: row.sourceFingerprint,
        employee_id: row.transaction.employeeId,
        department_id: row.transaction.departmentId,
        transaction_code: row.transaction.transactionCode,
        description: row.transaction.description,
        source_category: row.transaction.sourceCategory,
        business_category: row.transaction.businessCategory,
        normalized_category: row.transaction.normalizedCategory,
        category_confidence: row.transaction.categoryConfidence,
        category_reason: row.transaction.categoryReason,
        transaction_type: row.transaction.transactionType,
        transaction_eligibility: row.transaction.transactionEligibility,
        network_category_code: row.transaction.networkCategoryCode,
        policy_category: row.transaction.policyCategory,
        category_source: row.transaction.categorySource,
        normalized_merchant_family: row.transaction.normalizedMerchantFamily,
        amount_bucket: row.transaction.amountBucket,
        posting_delay_days: row.transaction.postingDelayDays,
        is_account_activity: row.transaction.isAccountActivity,
        is_credit_or_refund: row.transaction.isCreditOrRefund,
        is_foreign_transaction: row.transaction.isForeignTransaction,
        posting_date: row.transaction.postingDate,
        transaction_date: row.transaction.transactionDate,
        merchant_name: row.transaction.merchantName,
        normalized_merchant_name: row.transaction.normalizedMerchantName,
        amount_original: row.transaction.amountOriginal,
        amount_cad: row.transaction.amountCad,
        debit_credit: row.transaction.debitCredit,
        merchant_category_code: row.transaction.merchantCategoryCode,
        merchant_city: row.transaction.merchantCity,
        merchant_country: row.transaction.merchantCountry,
        merchant_postal_code: row.transaction.merchantPostalCode,
        merchant_region: row.transaction.merchantRegion,
        conversion_rate: row.transaction.conversionRate,
        business_purpose: null,
        guest_names: [],
      },
    }))
  }

  async function runPreview(nextCsvText: string) {
    setIsWorking(true)
    setError(null)
    setImportResult(null)
    setValidationResult(null)

    try {
      const employees = await listSyntheticAssignmentEmployees()

      if (employees.length === 0) {
        throw new Error('No synthetic employees found. Run the Supabase migrations and seed files first.')
      }

      const nextParseResult = parseTransactionCsv(nextCsvText, employees)
      setParseResult(nextParseResult)

      if (nextParseResult.rows.length > 0 && nextParseResult.missingColumns.length === 0) {
        const backendRows = serializeRowsForBackend(nextParseResult.rows)
        setValidationResult(
          await validateTransactionDataQuality({
            rows: backendRows.map((row) => row.transaction),
            run_great_expectations: false,
          }),
        )
      }
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : 'Could not preview the CSV.')
    } finally {
      setIsWorking(false)
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]

    if (!file) {
      return
    }

    setError(null)
    setImportResult(null)
    setValidationResult(null)
    setParseResult(null)
    setSourceFileName(file.name)
    setCsvText(await readFileAsText(file))
  }

  useEffect(() => {
    const trimmedCsvText = csvText.trim()

    if (!trimmedCsvText) {
      setParseResult(null)
      setValidationResult(null)
      setImportResult(null)
      setError(null)
      setIsWorking(false)
      return
    }

    const timeoutId = window.setTimeout(() => {
      void runPreview(csvText)
    }, 320)

    return () => window.clearTimeout(timeoutId)
  }, [csvText])

  async function handleImport() {
    if (!parseResult) {
      return
    }

    setIsWorking(true)
    setError(null)

    try {
      const backendRows = serializeRowsForBackend(parseResult.rows)
      const response = await importTransactions({
        source_file_name: sourceFileName,
        rows: backendRows,
        run_data_quality: true,
        run_great_expectations: false,
      })
      setImportResult(response)
      setValidationResult(response.validation)
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : 'Could not import transactions.')
    } finally {
      setIsWorking(false)
    }
  }

  return (
    <PageScaffold
      eyebrow={t('import.eyebrow')}
      title={t('import.title')}
      description={t('import.description')}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="surface-panel p-4">
          <div className="flex flex-col gap-4">
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-primary/40 bg-primary/5 px-4 py-8 text-center transition-colors hover:border-primary hover:bg-primary/10">
              <Upload className="size-6 text-primary" aria-hidden="true" />
              <span className="mt-2 text-sm font-medium text-foreground">{t('import.chooseCsv')}</span>
              <span className="mt-1 text-xs text-muted-foreground">{sourceFileName ?? t('import.dataSourceHint')}</span>
              <input className="sr-only" type="file" accept=".csv,.txt,text/csv,text/plain" onChange={handleFileChange} />
            </label>

            <label className="grid gap-2">
              <span className="text-sm font-medium text-foreground">{t('import.csvText')}</span>
              <textarea
                value={csvText}
                onChange={(event) => {
                  setCsvText(event.target.value)
                  setSourceFileName(null)
                }}
                className="min-h-48 resize-y rounded-lg border border-input bg-background/80 p-3 font-mono text-xs leading-5 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                placeholder={t('import.placeholder')}
              />
            </label>

            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" onClick={handleImport} disabled={isWorking || !canImport}>
                <Database className="size-4" aria-hidden="true" />
                {t('actions.import')}
              </Button>
            </div>
          </div>
        </section>

        <aside className="surface-panel p-4">
          <p className="text-sm font-semibold text-foreground">{t('import.statusTitle')}</p>
          <div className="mt-4 space-y-3 text-sm text-muted-foreground">
            <p>{t('import.sourceLabel')}: {sourceFileName ?? t('import.sourcePasted')}</p>
            <p>{t('import.rowsReady')}: {parseResult?.rows.length ?? 0}</p>
            <p>{t('import.previewRowsLabel')}: {previewRows.length}</p>
            <p>{t('import.readinessLabel')}: {canImport ? t('import.readinessReady') : t('import.readinessNeedsAttention')}</p>
            {importResult ? (
              <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-foreground">
                <div className="flex items-center gap-2 font-medium">
                  <CheckCircle2 className="size-4" aria-hidden="true" />
                  {t('import.importComplete')}
                </div>
                <p className="mt-2">{t('import.inserted')} {importResult.inserted_count} {t('import.transactions')}</p>
                <p>{t('import.skipped')} {importResult.skipped_duplicate_count} duplicates.</p>
                <p className="mt-1 text-xs text-muted-foreground">Backend enrichment applied to {importResult.authoritative_enrichment_applied} row(s).</p>
                {importResult.warnings.map((warning) => (
                  <p key={warning} className="mt-1 text-xs text-muted-foreground">{warning}</p>
                ))}
              </div>
            ) : null}
            {error ? <p className="rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">{error}</p> : null}
          </div>
        </aside>
      </div>

      {parseResult && parseResult.missingColumns.length > 0 ? (
        <section className="rounded-lg border border-amber-300/70 bg-amber-100/70 p-4 text-sm text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-100">
          <p className="font-semibold">{t('import.missingColumnsTitle')}</p>
          <p className="mt-2">{parseResult.missingColumns.join(', ')}</p>
        </section>
      ) : null}

      {previewRows.length > 0 ? (
        <section className="surface-panel overflow-hidden">
          <div className="border-b border-border/70 p-4">
            <p className="text-sm font-semibold text-foreground">{t('import.previewTitle')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('import.previewBody')}</p>
          </div>
          <div className="max-h-[32rem] overflow-auto">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="table-head">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('import.row')}</th>
                  <th className="px-4 py-3 font-medium">{t('import.date')}</th>
                  <th className="px-4 py-3 font-medium">{t('import.merchant')}</th>
                  <th className="px-4 py-3 font-medium">{t('import.category')}</th>
                  <th className="px-4 py-3 text-right font-medium">{t('import.amountCad')}</th>
                  <th className="px-4 py-3 font-medium">{t('import.syntheticEmployee')}</th>
                  <th className="px-4 py-3 font-medium">{t('import.fingerprint')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/70">
                {previewRows.map((row) => (
                  <tr key={row.sourceFingerprint} className="table-row">
                    <td className="px-4 py-3 text-muted-foreground">{row.sourceRowNumber}</td>
                    <td className="px-4 py-3 text-muted-foreground">{row.transaction.transactionDate}</td>
                    <td className="px-4 py-3 font-medium text-foreground">{row.transaction.normalizedMerchantName}</td>
                    <td className="px-4 py-3 text-muted-foreground">{row.transaction.businessCategory}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-foreground">
                      {currencyFormatter.format(row.transaction.amountCad)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {row.transaction.employeeName ?? t('import.unassigned')} / {row.transaction.departmentName ?? t('transactions.syntheticDepartment')}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{row.sourceFingerprint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </PageScaffold>
  )
}
