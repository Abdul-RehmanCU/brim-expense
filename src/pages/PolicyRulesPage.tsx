import {
  AlertTriangle,
  ClipboardCheck,
  FileSearch,
  FileText,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Trash2,
  Upload,
  Wand2,
} from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { PageScaffold } from '@/components/layout/PageScaffold'
import { Button } from '@/components/ui/button'
import {
  createPolicyDocumentFromText,
  extractPolicyRules,
  extractPolicyRulesFromDocument,
  listPolicyRules,
  resetPolicyData,
  scanPolicy,
  updatePolicyRule,
  uploadPolicyDocumentPdf,
  type PolicyDocumentCreateResponse,
  type PolicyDocumentItem,
  type PolicyRuleExtractionResponse,
  type PolicyRuleItem,
  type PolicyRuleStatus,
  type PolicySeverity,
} from '@/lib/api/backendClient'
import { useAssistantPageContext } from '@/lib/assistant/AssistantProvider'
import { useUiPreferences } from '@/lib/ui/preferences'

type IngestMode = 'text' | 'pdf'
type ReviewSignalTone = 'blocker' | 'warning' | 'positive'
type RuleReviewSignal = {
  key: string
  label: string
  detail: string
  tone: ReviewSignalTone
  blocksAutoAccept: boolean
}
type RuleReviewAnalysis = {
  signals: RuleReviewSignal[]
  autoAcceptable: boolean
  blockingSignals: RuleReviewSignal[]
}

const DRAFT_EDITOR_COPY = {
  extractedDrafts: 'Extracted rules',
  extractedDraftsBody: 'Safe rules activate automatically. Anything left here still needs follow-up before it can be enforced.',
  inspectJson: 'Inspect JSON',
}

const PAGE_COPY = {
  activationBlocked: 'Rule remains in draft because validation still needs attention.',
  ambiguities: 'Ambiguities',
  advancedJson: 'Canonical rule JSON',
  charCount: '{count} characters',
  defaultDocumentTitle: 'Policy document',
  documentExtracted: 'Text extracted',
  documentFailed: 'Extraction failed',
  documentPending: 'Pending extraction',
  documentSaved: 'Saved {title} with {count} characters ready for extraction.',
  documentTitle: 'Document title',
  documentTitlePlaceholder: 'Global policy handbook',
  activatedAutomatically: '{count} activated automatically',
  draftCount: '{count} rules extracted',
  draftReview: 'Draft review',
  draftReviewBody: 'Policy extraction now auto-activates safe rules. Any remaining drafts are the exceptions that still need cleanup or a deliberate override.',
  extractDrafts: 'Extract draft rules',
  extractError: 'Could not extract draft rules.',
  extractedResults: 'Extraction results',
  extractedResultsBody: 'Review the model summary, activation outcome, and any remaining blockers from the latest extraction run.',
  extractionComplete: 'Extracted {count} draft rules from {title}.',
  extractionWorkflowRefresh: 'Activated safe rules and refreshed downstream reviews automatically.',
  extracting: 'Extracting...',
  followUpNeeded: '{count} still need follow-up',
  ingestError: 'Could not save the policy source.',
  ingesting: 'Saving...',
  noActiveRules: 'No active rules yet.',
  noDocumentYet: 'No policy source is ready yet.',
  noDraftRules: 'No draft rules are available yet.',
  noExtractionYet: 'No extraction has run yet.',
  noSummary: 'No extraction summary was returned.',
  pasteText: 'Paste text',
  pdfFile: 'PDF file',
  pdfHint: 'Upload a text-based policy PDF for extraction.',
  pdfScannedError: 'This PDF could not be converted into extractable text.',
  policySource: 'Policy source',
  policySourceBody: 'Paste policy text or upload a PDF, then extract draft declarative rules for review.',
  preview: 'Preview',
  resetAction: 'Clear policy data',
  resetBody:
    'Remove old policy rules, saved policy documents, extraction runs, policy checks, violations, and synthetic policy evidence so a new PDF can be tested from a clean slate.',
  resetConfirm:
    'Clear all policy rules, saved policy documents, extraction runs, policy checks, violations, and synthetic policy evidence? This cannot be undone.',
  resetError: 'Could not clear existing policy data.',
  resetSuccess: 'Cleared legacy policy data. You can upload a fresh policy PDF now.',
  resetWarningPrefix: 'Reset completed with warnings:',
  resetting: 'Clearing...',
  runCompleted: 'Run completed',
  runFailed: 'Run failed',
  runPending: 'Run pending',
  activateOverride: 'Activate override',
  activatedAndRefreshed: 'Rule activated and downstream reviews refreshed.',
  disabledAndRefreshed: 'Rule disabled and downstream reviews refreshed.',
  followUpRules: 'Follow-up rules',
  followUpSummary: 'These rules were saved, but backend guardrails or validation still blocked automatic activation.',
  manualOverrideHint: 'You can still test a rule or activate it deliberately if you want to override the backend guardrails.',
  reviewSignals: 'Review signals',
  runWorkflowRefresh: 'Refresh scan + reviews',
  runWorkflowRefreshComplete: 'Policy scan refreshed {count} transactions and updated downstream reviews with {flags} flags.',
  skippedReasons: 'Skipped reasons',
  savePdf: 'Save PDF source',
  savePolicyText: 'Save text source',
  selectPdf: 'Select a PDF to upload.',
  sourceAiExtracted: 'AI extracted',
  sourceManual: 'Manual',
  sourcePastedText: 'Pasted text',
  sourceSeeded: 'Seeded',
  sourceUploadedPdf: 'Uploaded PDF',
  suggestedFeatures: 'Suggested feature work',
  unsupportedFields: 'Unsupported or missing fields',
  uploadPdf: 'Upload PDF',
} as const

const policyRulesPageSize = 25

export function PolicyRulesPage() {
  const [rules, setRules] = useState<PolicyRuleItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isExtracting, setIsExtracting] = useState(false)
  const [isIngesting, setIsIngesting] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [isResetting, setIsResetting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [ingestMode, setIngestMode] = useState<IngestMode>('text')
  const [documentTitle, setDocumentTitle] = useState('')
  const [policyText, setPolicyText] = useState('')
  const [policyFile, setPolicyFile] = useState<File | null>(null)
  const [currentDocument, setCurrentDocument] = useState<PolicyDocumentItem | null>(null)
  const [extractionResult, setExtractionResult] = useState<PolicyRuleExtractionResponse | null>(null)
  const { t } = useUiPreferences()

  const activeRules = useMemo(() => rules.filter((rule) => rule.status === 'active'), [rules])
  const currentDocumentText = currentDocument?.extracted_text ?? currentDocument?.raw_text ?? ''
  const textExtractionSource = useMemo(() => {
    if (policyText.trim()) {
      return policyText.trim()
    }
    if (ingestMode === 'text' && currentDocument?.source_type === 'pasted_text') {
      return currentDocumentText
    }
    return ''
  }, [currentDocument?.source_type, currentDocumentText, ingestMode, policyText])
  const canExtractDraftRules =
    ingestMode === 'text'
      ? textExtractionSource.trim().length >= 20
      : currentDocument?.source_type === 'uploaded_pdf' && currentDocument.extraction_status === 'extracted'

  const reviewRules = useMemo(() => {
    const nonActiveRules = rules.filter((rule) => rule.status !== 'active')
    const focusedDocumentId = extractionResult ? extractionResult.policy_document_id : currentDocument?.id
    if (!focusedDocumentId) {
      return nonActiveRules
    }

    const linkedRules = nonActiveRules.filter((rule) => rule.policy_document_id === focusedDocumentId)
    return linkedRules.length > 0 ? linkedRules : nonActiveRules
  }, [currentDocument?.id, extractionResult, rules])
  const reviewableDraftRules = useMemo(() => reviewRules.filter((rule) => rule.status === 'draft'), [reviewRules])
  const reviewAnalysisById = useMemo(() => buildRuleReviewAnalysis(reviewRules), [reviewRules])
  const extractedActiveRules = useMemo(
    () => (extractionResult?.draft_rules ?? []).filter((rule) => rule.status === 'active'),
    [extractionResult],
  )
  const extractedFollowUpRules = useMemo(
    () => (extractionResult?.draft_rules ?? []).filter((rule) => rule.status !== 'active'),
    [extractionResult],
  )
  const skippedReasonCounts = useMemo(
    () => countSkippedReasons(reviewableDraftRules, reviewAnalysisById),
    [reviewAnalysisById, reviewableDraftRules],
  )
  const assistantContext = useMemo(
    () => ({
      routeId: 'policyRules' as const,
      title: 'Policy Setup',
      summary: currentDocument
        ? `Working with ${currentDocument.title} and ${reviewRules.length} draft or review rule${reviewRules.length === 1 ? '' : 's'}.`
        : 'Manage policy ingestion, extraction, and review rules.',
      focus: currentDocument
        ? {
            type: 'policy_document',
            id: currentDocument.id,
            label: currentDocument.title,
            status: currentDocument.extraction_status,
          }
        : null,
      focusEntities: currentDocument
        ? [
            {
              type: 'policy_document',
              id: currentDocument.id,
              label: currentDocument.title,
              status: currentDocument.extraction_status,
              attributes: {
                source_type: currentDocument.source_type,
                active: currentDocument.active,
              },
            },
          ]
        : [],
      visibleEntities: reviewRules.slice(0, 8).map((rule) => ({
        type: 'policy_rule',
        id: rule.id,
        label: rule.name,
        status: rule.status,
        attributes: {
          rule_code: rule.rule_code,
          severity: rule.severity,
          enabled: rule.enabled,
          needs_human_review: rule.needs_human_review,
        },
      })),
      artifacts: currentDocument
        ? [
            {
              type: 'policy_source',
              id: currentDocument.id,
              label: currentDocument.title,
              status: currentDocument.extraction_status,
              metadata: {
                source_type: currentDocument.source_type,
              },
            },
          ]
        : [],
      metrics: {
        active_rules: activeRules.length,
        review_rules: reviewRules.length,
        draft_count: extractionResult?.draft_rules.length ?? 0,
      },
      availableViews: ['policy source', 'draft review', 'active rules'],
      suggestions: [
        'Summarize the current extraction run.',
        'What draft rules still need review?',
      ],
    }),
    [activeRules.length, currentDocument, extractionResult?.draft_rules.length, reviewRules.length],
  )
  useAssistantPageContext(assistantContext)

  function resetPolicyWorkspace() {
    setRules([])
    setCurrentDocument(null)
    setExtractionResult(null)
    setDocumentTitle('')
    setPolicyText('')
    setPolicyFile(null)
  }

  function syncRuleState(updated: PolicyRuleItem) {
    setRules((currentRules) => currentRules.map((rule) => (rule.id === updated.id ? updated : rule)))
    setExtractionResult((currentResult) => {
      if (!currentResult) {
        return currentResult
      }
      return {
        ...currentResult,
        draft_rules: currentResult.draft_rules.map((rule) => (rule.id === updated.id ? { ...rule, ...updated } : rule)),
      }
    })
  }

  async function loadRules() {
    setIsLoading(true)
    setError(null)

    try {
      const loadedRules = await listPolicyRules({ limit: policyRulesPageSize })
      setRules(loadedRules)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : t('policyRules.loadError'))
    } finally {
      setIsLoading(false)
    }
  }

  async function extractRulesFromTextSource() {
    const normalizedEditorText = normalizeEditorText(policyText)
    const normalizedDocumentText = normalizeEditorText(currentDocumentText)

    if (
      currentDocument?.source_type === 'pasted_text' &&
      normalizedDocumentText &&
      (!normalizedEditorText || normalizedDocumentText === normalizedEditorText)
    ) {
      return extractPolicyRulesFromDocument(currentDocument.id)
    }

    const sourceText = textExtractionSource.trim()
    if (!sourceText) {
      throw new Error('Paste policy text before extracting draft rules.')
    }

    return extractPolicyRules({
      policy_text: sourceText,
    })
  }

  async function ingestCurrentSource() {
    setIsIngesting(true)
    setError(null)
    setStatusMessage(null)
    setExtractionResult(null)

    try {
      let response: PolicyDocumentCreateResponse
      if (ingestMode === 'text') {
        response = await createPolicyDocumentFromText({
          title: documentTitle.trim() || PAGE_COPY.defaultDocumentTitle,
          policy_text: policyText,
        })
      } else {
        if (!policyFile) {
          throw new Error(PAGE_COPY.selectPdf)
        }
        response = await uploadPolicyDocumentPdf(policyFile, documentTitle.trim() || undefined)
      }

      setCurrentDocument(response.document)
      setStatusMessage(
        response.document.extraction_status === 'failed'
          ? response.document.extraction_error ?? PAGE_COPY.pdfScannedError
          : PAGE_COPY.documentSaved
              .replace('{title}', response.document.title)
              .replace('{count}', response.char_count.toLocaleString()),
      )
    } catch (ingestError) {
      setError(ingestError instanceof Error ? ingestError.message : PAGE_COPY.ingestError)
    } finally {
      setIsIngesting(false)
    }
  }

  async function extractDraftRules() {
    setIsExtracting(true)
    setError(null)
    setStatusMessage(null)

    try {
      const result =
        ingestMode === 'text'
          ? await extractRulesFromTextSource()
          : currentDocument
            ? await extractPolicyRulesFromDocument(currentDocument.id)
            : null

      if (!result) {
        throw new Error(PAGE_COPY.noDocumentYet)
      }

      setExtractionResult(result)
      await loadRules()
      setStatusMessage(buildExtractionStatusMessage(result, currentDocument?.title ?? t('policyRules.policyText')))
    } catch (extractError) {
      setError(extractError instanceof Error ? extractError.message : PAGE_COPY.extractError)
    } finally {
      setIsExtracting(false)
    }
  }

  async function activateRule(rule: PolicyRuleItem) {
    setError(null)
    setStatusMessage(null)

    try {
      setIsScanning(true)
      const updated = await updatePolicyRule(rule.id, { enabled: true, status: 'active' })
      syncRuleState(updated)
      if (updated.status === 'active') {
        await runScanWithActiveRules(PAGE_COPY.activatedAndRefreshed)
      } else {
        setStatusMessage(PAGE_COPY.activationBlocked)
      }
    } catch (activationError) {
      setError(activationError instanceof Error ? activationError.message : t('policyRules.updateError'))
    } finally {
      setIsScanning(false)
    }
  }

  async function disableRule(rule: PolicyRuleItem) {
    setError(null)
    setStatusMessage(null)

    try {
      setIsScanning(true)
      const updated = await updatePolicyRule(rule.id, { enabled: false, status: 'disabled' })
      syncRuleState(updated)
      await runScanWithActiveRules(PAGE_COPY.disabledAndRefreshed)
    } catch (disableError) {
      setError(disableError instanceof Error ? disableError.message : t('policyRules.updateError'))
    } finally {
      setIsScanning(false)
    }
  }

  async function runScanWithActiveRules(successMessage?: string) {
    setError(null)
    setStatusMessage(null)

    try {
      const summary = await scanPolicy({
        batch_size: 500,
        reset_existing: true,
        reset_synthetic_evidence: true,
      })
      setStatusMessage(
        successMessage ??
          PAGE_COPY.runWorkflowRefreshComplete
          .replace('{count}', summary.total_scanned.toLocaleString())
          .replace('{flags}', summary.individual_flags.toLocaleString()),
      )
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : t('policyRules.scanError'))
    }
  }

  async function clearExistingPolicyData() {
    const confirmed = window.confirm(PAGE_COPY.resetConfirm)
    if (!confirmed) {
      return
    }

    setIsResetting(true)
    setError(null)
    setStatusMessage(null)

    try {
      const result = await resetPolicyData()
      resetPolicyWorkspace()
      await loadRules()
      setStatusMessage(
        result.warnings.length > 0
          ? `${PAGE_COPY.resetSuccess} ${PAGE_COPY.resetWarningPrefix} ${result.warnings.join(' ')}`
          : PAGE_COPY.resetSuccess,
      )
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : PAGE_COPY.resetError)
    } finally {
      setIsResetting(false)
    }
  }

  useEffect(() => {
    let ignore = false

    async function loadInitialRules() {
      try {
        const loadedRules = await listPolicyRules({ limit: policyRulesPageSize })
        if (!ignore) {
          setRules(loadedRules)
        }
      } catch (loadError) {
        if (!ignore) {
          setError(loadError instanceof Error ? loadError.message : t('policyRules.loadError'))
        }
      } finally {
        if (!ignore) {
          setIsLoading(false)
        }
      }
    }

    void loadInitialRules()

    return () => {
      ignore = true
    }
  }, [t])

  return (
    <PageScaffold
      eyebrow={t('policyRules.eyebrow')}
      title={t('policyRules.title')}
      description={t('policyRules.description')}
    >
      <section className="grid items-start gap-4 min-[1200px]:grid-cols-[minmax(0,1.14fr)_minmax(320px,0.86fr)]">
        <div className="grid gap-4">
          <section className="surface-panel overflow-hidden">
            <div className="flex items-start gap-3 border-b border-border/70 p-4">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Upload className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">{PAGE_COPY.policySource}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{PAGE_COPY.policySourceBody}</p>
                </div>
              </div>
            </div>

            <div className="grid gap-4 p-4 min-[1100px]:grid-cols-[minmax(0,1fr)_18rem]">
              <div className="grid gap-3">
                <div className="flex flex-wrap gap-2">
                  {(['text', 'pdf'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={`rounded-lg border px-3 py-1.5 text-sm whitespace-nowrap ${
                        ingestMode === mode
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-background text-muted-foreground'
                      }`}
                      onClick={() => setIngestMode(mode)}
                    >
                      {mode === 'text' ? PAGE_COPY.pasteText : PAGE_COPY.uploadPdf}
                    </button>
                  ))}
                </div>

                {ingestMode === 'text' ? (
                  <label className="grid gap-1 text-sm">
                    <span className="font-medium text-foreground">{t('policyRules.policyText')}</span>
                    <textarea
                      className="max-h-80 min-h-[11rem] resize-y rounded-lg border border-input bg-background p-3 text-sm text-foreground outline-none focus:border-primary min-[1100px]:min-h-[12rem]"
                      value={policyText}
                      onChange={(event) => setPolicyText(event.target.value)}
                      placeholder={t('policyRules.policyTextPlaceholder')}
                    />
                  </label>
                ) : (
                  <label className="grid gap-2 text-sm">
                    <span className="font-medium text-foreground">{PAGE_COPY.pdfFile}</span>
                    <input
                      className="block w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary/10 file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary"
                      type="file"
                      accept="application/pdf"
                      onChange={(event) => setPolicyFile(event.target.files?.[0] ?? null)}
                    />
                    <p className="text-sm text-muted-foreground">
                      {policyFile ? policyFile.name : PAGE_COPY.pdfHint}
                    </p>
                  </label>
                )}
              </div>

              <div className="grid content-start gap-3">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-foreground">{PAGE_COPY.documentTitle}</span>
                  <input
                    className="h-10 rounded-lg border border-input bg-background px-3 text-sm text-foreground outline-none focus:border-primary"
                    value={documentTitle}
                    onChange={(event) => setDocumentTitle(event.target.value)}
                    placeholder={PAGE_COPY.documentTitlePlaceholder}
                  />
                </label>

                <div className="grid gap-2">
                  <Button type="button" onClick={ingestCurrentSource} disabled={isIngesting || isResetting}>
                    <Upload className="size-4" aria-hidden="true" />
                    {isIngesting
                      ? PAGE_COPY.ingesting
                      : ingestMode === 'text'
                        ? PAGE_COPY.savePolicyText
                        : PAGE_COPY.savePdf}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={extractDraftRules}
                    disabled={!canExtractDraftRules || isExtracting || isResetting}
                  >
                    <Wand2 className="size-4" aria-hidden="true" />
                    {isExtracting ? PAGE_COPY.extracting : PAGE_COPY.extractDrafts}
                  </Button>
                </div>
              </div>

              <div className="min-[1100px]:col-span-2">
                <div className="rounded-lg border border-red-300/70 bg-red-100/60 p-3 dark:border-red-400/30 dark:bg-red-400/10">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-red-500/10 text-red-700 dark:text-red-100">
                        <AlertTriangle className="size-4" aria-hidden="true" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-red-800 dark:text-red-100">{PAGE_COPY.resetAction}</p>
                        <p className="mt-1 text-sm leading-5 text-red-700 dark:text-red-100/90">{PAGE_COPY.resetBody}</p>
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={clearExistingPolicyData}
                      disabled={isResetting || isIngesting || isExtracting || isScanning}
                    >
                      <Trash2 className="size-4" aria-hidden="true" />
                      {isResetting ? PAGE_COPY.resetting : PAGE_COPY.resetAction}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="surface-panel overflow-hidden">
            <div className="flex items-start gap-3 border-b border-border/70 p-4">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <ClipboardCheck className="size-4" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">{PAGE_COPY.followUpRules}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{PAGE_COPY.draftReviewBody}</p>
                </div>
              </div>
            </div>

            <div className="border-b border-border/70 bg-muted/60 px-4 py-3">
              <p className="text-sm text-muted-foreground">{PAGE_COPY.followUpSummary}</p>
              {reviewableDraftRules.length > 0 ? (
                <div className="mt-2 grid gap-2">
                  <p className="text-sm font-medium text-foreground">
                    {PAGE_COPY.followUpNeeded.replace('{count}', reviewableDraftRules.length.toLocaleString())}
                  </p>
                  {skippedReasonCounts.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {skippedReasonCounts.map((reason) => (
                        <span key={reason.label} className="status-chip bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100">
                          {reason.label}: {reason.count}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <p className="text-sm text-muted-foreground">{PAGE_COPY.manualOverrideHint}</p>
                </div>
              ) : null}
            </div>

            {isLoading ? <p className="p-4 text-sm text-muted-foreground">{t('policyRules.loading')}</p> : null}
            {!isLoading && reviewRules.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">{PAGE_COPY.noDraftRules}</p>
            ) : null}

            {reviewRules.length > 0 ? (
              <div className="max-h-[48rem] divide-y divide-border/70 overflow-y-auto">
                {reviewRules.map((rule) => {
                  const reviewAnalysis = reviewAnalysisById[rule.id]

                  return (
                  <article key={rule.id} className="grid gap-3 px-4 py-3 min-[1100px]:grid-cols-[minmax(0,1fr)_11rem]">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">{rule.rule_code}</span>
                        <RuleStatusPill status={rule.status} />
                        <SeverityPill severity={rule.severity} />
                        {reviewAnalysis?.autoAcceptable ? <RecommendedPill /> : null}
                        <span className="status-chip bg-muted text-muted-foreground">
                          {formatSourceType(rule.source_type)}
                        </span>
                      </div>
                      <h2 className="mt-2 text-base font-semibold text-foreground">{rule.name}</h2>
                      <p className="mt-1 text-sm leading-5 text-muted-foreground">{rule.description}</p>
                      {rule.source_text ? (
                        <p className="mt-2.5 text-sm leading-5 text-foreground">{summarizeText(rule.source_text, 180)}</p>
                      ) : null}
                      {rule.validation_errors.length > 0 ? (
                        <ul className="mt-2.5 list-disc space-y-1 pl-4 text-sm text-red-700 dark:text-red-100">
                          {rule.validation_errors.map((validationError) => (
                            <li key={validationError}>{validationError}</li>
                          ))}
                        </ul>
                      ) : null}
                      {reviewAnalysis ? <RuleReviewSignals analysis={reviewAnalysis} /> : null}
                      <RuleJsonDetails ruleJson={rule.rule_json} />
                    </div>
                    <div className="flex flex-wrap items-start justify-start gap-2 min-[1100px]:flex-col min-[1100px]:items-stretch">
                      {rule.status === 'active' ? (
                        <Button type="button" size="sm" variant="outline" onClick={() => disableRule(rule)}>
                          <ToggleLeft className="size-4" aria-hidden="true" />
                          {t('policyRules.disable')}
                        </Button>
                      ) : (
                        <Button type="button" size="sm" onClick={() => activateRule(rule)}>
                          <ToggleRight className="size-4" aria-hidden="true" />
                          {PAGE_COPY.activateOverride}
                        </Button>
                      )}
                    </div>
                  </article>
                  )
                })}
              </div>
            ) : null}
          </section>
        </div>

        <aside className="grid gap-4">
          <section className="surface-panel overflow-hidden">
            <div className="flex items-start gap-3 border-b border-border/70 p-4">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileSearch className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{PAGE_COPY.extractedResults}</p>
                <p className="mt-1 text-sm text-muted-foreground">{PAGE_COPY.extractedResultsBody}</p>
              </div>
            </div>

            <div className="grid gap-3 p-4">
              {currentDocument ? (
                <article className="rounded-lg border border-border/70 bg-background p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <DocumentStatusPill status={currentDocument.extraction_status} />
                    <span className="status-chip bg-muted text-muted-foreground">
                      {formatSourceType(currentDocument.source_type)}
                    </span>
                    <span className="status-chip bg-muted text-muted-foreground">
                      {PAGE_COPY.charCount.replace(
                        '{count}',
                        ((currentDocument.extracted_text ?? currentDocument.raw_text ?? '').length || 0).toLocaleString(),
                      )}
                    </span>
                  </div>
                  <h2 className="mt-3 text-base font-semibold text-foreground">{currentDocument.title}</h2>
                  {currentDocument.extraction_error ? (
                    <p className="mt-2 rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">
                      {currentDocument.extraction_error}
                    </p>
                  ) : null}
                  {currentDocument.extracted_text || currentDocument.raw_text ? (
                    <div className="mt-3 max-h-56 overflow-y-auto rounded-lg border border-border/70 bg-muted/40 p-3">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {PAGE_COPY.preview}
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground">
                        {summarizeText(currentDocument.extracted_text ?? currentDocument.raw_text ?? '', 700)}
                      </p>
                    </div>
                  ) : null}
                </article>
              ) : (
                <p className="text-sm text-muted-foreground">{PAGE_COPY.noDocumentYet}</p>
              )}

              {extractionResult ? (
                <article className="rounded-lg border border-border/70 bg-background p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="status-chip bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100">
                      {PAGE_COPY.draftCount.replace('{count}', extractionResult.draft_rules.length.toLocaleString())}
                    </span>
                    <span className="status-chip bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100">
                      {PAGE_COPY.activatedAutomatically.replace(
                        '{count}',
                        extractedActiveRules.length.toLocaleString(),
                      )}
                    </span>
                    <span className="status-chip bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100">
                      {PAGE_COPY.followUpNeeded.replace('{count}', extractedFollowUpRules.length.toLocaleString())}
                    </span>
                    {extractionResult.extraction_run ? (
                      <span className="status-chip bg-muted text-muted-foreground">
                        {formatRunStatus(extractionResult.extraction_run.status)}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-3 max-h-32 overflow-y-auto pr-1 text-sm text-foreground">{extractionResult.summary || PAGE_COPY.noSummary}</p>
                  {extractedActiveRules.length > 0 ? (
                    <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-100">
                      {PAGE_COPY.extractionWorkflowRefresh}
                    </p>
                  ) : null}

                  <ExtractionList
                    title={PAGE_COPY.ambiguities}
                    icon={<AlertTriangle className="size-4" aria-hidden="true" />}
                    items={extractionResult.ambiguities}
                  />
                  <ExtractionList
                    title={PAGE_COPY.unsupportedFields}
                    icon={<AlertTriangle className="size-4" aria-hidden="true" />}
                    items={extractionResult.unsupported_or_missing_fields}
                  />
                  <ExtractionList
                    title={PAGE_COPY.suggestedFeatures}
                    icon={<Sparkles className="size-4" aria-hidden="true" />}
                    items={extractionResult.suggested_feature_engineering}
                  />

                  {extractionResult.draft_rules.length > 0 ? (
                    <div className="mt-3 rounded-lg border border-border/70 bg-muted/30 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-foreground">{DRAFT_EDITOR_COPY.extractedDrafts}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{DRAFT_EDITOR_COPY.extractedDraftsBody}</p>
                        </div>
                      </div>
                      <div className="mt-3 grid max-h-[28rem] gap-2.5 overflow-y-auto pr-1">
                        {extractionResult.draft_rules.map((rule) => (
                          <article key={rule.rule_code} className="rounded-lg border border-border/70 bg-background p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-xs text-muted-foreground">{rule.rule_code}</span>
                              <SeverityPill severity={rule.severity} />
                            </div>
                            <p className="mt-2 text-sm font-medium text-foreground">{rule.name}</p>
                            <p className="mt-1 text-sm text-muted-foreground">{rule.description}</p>
                            {rule.source_text ? (
                              <p className="mt-2 text-sm leading-5 text-foreground">{summarizeText(rule.source_text, 140)}</p>
                            ) : null}
                            <RuleJsonDetails ruleJson={rule.rule_json} />
                          </article>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </article>
              ) : (
                <p className="text-sm text-muted-foreground">{PAGE_COPY.noExtractionYet}</p>
              )}
            </div>
          </section>

          <section className="surface-panel overflow-hidden">
            <div className="flex items-start gap-3 border-b border-border/70 p-4">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileText className="size-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{t('policyRules.ruleLibrary')}</p>
                <p className="mt-1 text-sm text-muted-foreground">{t('policyRules.ruleLibraryBody')}</p>
              </div>
            </div>

            {activeRules.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">{PAGE_COPY.noActiveRules}</p>
            ) : (
              <div className="max-h-[28rem] divide-y divide-border/70 overflow-y-auto">
                {activeRules.map((rule) => (
                  <article key={rule.id} className="grid gap-2 px-4 py-3">
                    <div className="min-w-0 grid gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="max-w-full break-all font-mono text-xs text-muted-foreground">{rule.rule_code}</span>
                        <RuleStatusPill status={rule.status} />
                        <SeverityPill severity={rule.severity} />
                      </div>
                      <div className="min-w-0">
                        <h2 className="text-base font-semibold text-foreground">{rule.name}</h2>
                        <p className="mt-1 text-sm leading-5 text-muted-foreground">{rule.description}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button type="button" size="sm" variant="outline" onClick={() => disableRule(rule)}>
                        <ToggleLeft className="size-4" aria-hidden="true" />
                        {t('policyRules.disable')}
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          {statusMessage ? (
            <p className="rounded-lg border border-border bg-muted p-3 text-sm text-foreground">{statusMessage}</p>
          ) : null}
          {error ? (
            <p className="rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">
              {error}
            </p>
          ) : null}
        </aside>
      </section>
    </PageScaffold>
  )
}

function RuleStatusPill({ status }: { status: PolicyRuleStatus }) {
  const { t } = useUiPreferences()
  const className =
    status === 'active'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100'
      : status === 'draft'
        ? 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'
        : 'bg-muted text-muted-foreground'

  return <span className={`status-chip ${className}`}>{formatRuleStatus(status, t)}</span>
}

function SeverityPill({ severity }: { severity: PolicySeverity }) {
  const { t } = useUiPreferences()
  const className =
    severity === 'critical'
      ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
      : severity === 'high'
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
        : severity === 'medium'
          ? 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'
          : 'bg-muted text-muted-foreground'

  return <span className={`status-chip ${className}`}>{t(`policyRules.${severity}`)}</span>
}

function RecommendedPill() {
  return (
    <span className="status-chip bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100">
      Recommended
    </span>
  )
}

function RuleReviewSignals({ analysis }: { analysis: RuleReviewAnalysis }) {
  if (analysis.signals.length === 0) {
    return null
  }

  return (
    <div className="mt-3 rounded-lg border border-border/70 bg-muted/30 p-3">
      <p className="text-sm font-medium text-foreground">{PAGE_COPY.reviewSignals}</p>
      <div className="mt-2 flex max-h-28 flex-wrap gap-2 overflow-y-auto pr-1">
        {analysis.signals.map((signal) => (
          <span
            key={signal.key}
            className={`status-chip ${reviewSignalClassName(signal.tone)}`}
            title={signal.detail}
          >
            {signal.label}
          </span>
        ))}
      </div>
    </div>
  )
}

function DocumentStatusPill({ status }: { status: PolicyDocumentItem['extraction_status'] }) {
  const className =
    status === 'extracted'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100'
      : status === 'failed'
        ? 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
        : 'bg-blue-100 text-blue-700 dark:bg-blue-400/15 dark:text-blue-100'

  return <span className={`status-chip ${className}`}>{formatDocumentStatus(status)}</span>
}

function ExtractionList({
  title,
  icon,
  items,
}: {
  title: string
  icon: ReactNode
  items: string[]
}) {
  if (items.length === 0) {
    return null
  }

  return (
    <div className="mt-4 rounded-lg border border-border/70 bg-muted/30 p-3">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        {icon}
        <span>{title}</span>
      </div>
      <ul className="mt-2 max-h-36 list-disc space-y-1 overflow-y-auto pl-4 pr-1 text-sm text-muted-foreground">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function RuleJsonDetails({ ruleJson }: { ruleJson: unknown }) {
  return (
    <details className="mt-2.5 rounded-lg border border-border/70 bg-muted/30 p-2.5">
      <summary className="cursor-pointer text-sm font-medium text-foreground">
        {DRAFT_EDITOR_COPY.inspectJson}
      </summary>
      <div className="mt-2 max-h-72 overflow-y-auto rounded-md border border-border/60 bg-background/80 p-2">
        <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-5 text-muted-foreground">
          {JSON.stringify(ruleJson, null, 2)}
        </pre>
      </div>
    </details>
  )
}

function summarizeText(text: string, limit: number) {
  if (text.length <= limit) {
    return text
  }

  return `${text.slice(0, limit).trimEnd()}...`
}

function buildExtractionStatusMessage(result: PolicyRuleExtractionResponse, title: string) {
  const activatedCount = result.draft_rules.filter((rule) => rule.status === 'active').length
  const followUpCount = result.draft_rules.length - activatedCount
  const baseMessage = PAGE_COPY.extractionComplete
    .replace('{count}', result.draft_rules.length.toLocaleString())
    .replace('{title}', title)

  if (activatedCount === 0) {
    return baseMessage
  }

  return `${baseMessage} ${PAGE_COPY.activatedAutomatically.replace('{count}', activatedCount.toLocaleString())}. ${PAGE_COPY.followUpNeeded.replace('{count}', followUpCount.toLocaleString())}. ${PAGE_COPY.extractionWorkflowRefresh}`
}

function normalizeEditorText(text: string) {
  return text.replace(/\s+/g, ' ').trim()
}

function buildRuleReviewAnalysis(rules: PolicyRuleItem[]): Record<string, RuleReviewAnalysis> {
  const analysisById: Record<string, RuleReviewAnalysis> = {}
  const duplicateGroups = new Map<string, PolicyRuleItem[]>()

  for (const rule of rules) {
    const signals = inspectRuleForReviewSignals(rule)
    analysisById[rule.id] = buildAnalysis(signals)

    if (rule.status === 'draft') {
      const duplicateKey = duplicateFamilyKey(rule)
      if (duplicateKey) {
        duplicateGroups.set(duplicateKey, [...(duplicateGroups.get(duplicateKey) ?? []), rule])
      }
    }
  }

  for (const group of duplicateGroups.values()) {
    if (group.length < 2) {
      continue
    }

    const representative = [...group].sort(compareDuplicateRepresentatives)[0]
    for (const rule of group) {
      if (rule.id === representative.id) {
        analysisById[rule.id] = buildAnalysis([
          ...analysisById[rule.id].signals,
          {
            key: 'duplicate-kept',
            label: 'Duplicate family',
            detail: 'Similar rules were extracted; this one is the best candidate to review first.',
            tone: 'warning',
            blocksAutoAccept: false,
          },
        ])
        continue
      }

      analysisById[rule.id] = buildAnalysis([
        ...analysisById[rule.id].signals,
        {
          key: 'duplicate-rule',
          label: 'Duplicate',
          detail: `Similar to ${representative.rule_code}; keep one rule family active at a time.`,
          tone: 'blocker',
          blocksAutoAccept: true,
        },
      ])
    }
  }

  return analysisById
}

function inspectRuleForReviewSignals(rule: PolicyRuleItem): RuleReviewSignal[] {
  const signals: RuleReviewSignal[] = []
  const fields = extractConditionFields(rule.rule_json?.condition)
  const fieldSet = new Set(fields)
  const combinedText = normalizeForReview(`${rule.rule_code} ${rule.name} ${rule.description} ${rule.source_text ?? ''}`)
  const appliesTo = getRuleObject(rule.rule_json?.applies_to)
  const requires = getRuleObject(rule.rule_json?.requires)
  const contextRequirements = getStringArray(rule.rule_json?.context_requirements)
  const requiredFacts = getStringArray(requires.facts)
  const hasCategoryOrMerchantScope =
    hasScopedAppliesTo(appliesTo) || fields.some((field) => CATEGORY_OR_MERCHANT_FIELDS.has(field))
  const hasAmountThreshold = fieldSet.has('amount_cad') || fieldSet.has('amount') || fieldSet.has('amount_original')
  const hasOnlyBroadActivityFields = fields.length > 0 && fields.every((field) => BROAD_ACTIVITY_FIELDS.has(field))
  const usesEvidenceFacts = [...fields, ...requiredFacts, ...contextRequirements].some(isEvidenceOrHumanJudgmentField)

  if (rule.validation_errors.length > 0) {
    signals.push({
      key: 'validation-errors',
      label: 'Invalid JSON',
      detail: 'Backend validation returned errors; fix the canonical rule before activation.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (fields.length === 0) {
    signals.push({
      key: 'no-condition-fields',
      label: 'No data fields',
      detail: 'The rule has no enforceable condition fields, so it cannot be safely evaluated.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (hasOnlyBroadActivityFields) {
    signals.push({
      key: 'broad-activity-only',
      label: 'Too broad',
      detail: 'The condition only checks debit/card activity/account activity, which can match nearly every row.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (fieldSet.has('debit_or_credit') && !hasCategoryOrMerchantScope && !hasAmountThreshold) {
    signals.push({
      key: 'debit-without-scope',
      label: 'Debit-only',
      detail: 'Debit/credit direction is not enough policy context for bulk activation.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (isGlobalReceiptRule(combinedText, hasCategoryOrMerchantScope)) {
    signals.push({
      key: 'global-receipt-rule',
      label: 'Global receipt',
      detail: 'A global receipt rule should wait until receipt evidence ingestion is working, otherwise it floods compliance.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (usesEvidenceFacts && !hasCategoryOrMerchantScope && !hasAmountThreshold) {
    signals.push({
      key: 'evidence-without-scope',
      label: 'Needs evidence',
      detail: 'This rule depends on evidence or human-review facts without a narrow transaction scope.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (contextRequirements.length > 0) {
    signals.push({
      key: 'context-requirements',
      label: 'Feature needed',
      detail: 'The rule lists context requirements that may need data capture before enforcement.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (rule.extraction_confidence !== null && rule.extraction_confidence < 0.78) {
    signals.push({
      key: 'low-confidence',
      label: 'Low confidence',
      detail: 'The extractor was not confident enough for bulk activation.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (containsGuidanceOnlyLanguage(combinedText) && !hasAmountThreshold && !hasCategoryOrMerchantScope) {
    signals.push({
      key: 'guidance-only',
      label: 'Judgment call',
      detail: 'Guidance words such as reasonable, excessive, or discretion need a human-defined threshold.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (containsConductOnlyLanguage(combinedText) && !hasDirectConductEvidence(fieldSet)) {
    signals.push({
      key: 'conduct-only',
      label: 'Conduct policy',
      detail: 'Conduct, fraud, safety, or named-card rules need direct evidence fields before automation.',
      tone: 'blocker',
      blocksAutoAccept: true,
    })
  }

  if (signals.length === 0 && rule.status === 'draft') {
    signals.push({
      key: 'recommended',
      label: 'Scoped rule',
      detail: 'This draft uses deterministic facts with enough scope for bulk activation.',
      tone: 'positive',
      blocksAutoAccept: false,
    })
  }

  return signals
}

function buildAnalysis(signals: RuleReviewSignal[]): RuleReviewAnalysis {
  const blockingSignals = signals.filter((signal) => signal.blocksAutoAccept)
  return {
    signals,
    blockingSignals,
    autoAcceptable: blockingSignals.length === 0,
  }
}

function countSkippedReasons(
  draftRules: PolicyRuleItem[],
  analysisById: Record<string, RuleReviewAnalysis>,
) {
  const counts = new Map<string, number>()
  for (const rule of draftRules) {
    const blockingSignal = analysisById[rule.id]?.blockingSignals[0]
    if (!blockingSignal) {
      continue
    }
    counts.set(blockingSignal.label, (counts.get(blockingSignal.label) ?? 0) + 1)
  }

  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
}

function extractConditionFields(condition: unknown): string[] {
  if (!condition || typeof condition !== 'object') {
    return []
  }

  const node = condition as Record<string, unknown>
  const nested = ['all', 'any']
    .flatMap((key) => (Array.isArray(node[key]) ? (node[key] as unknown[]) : []))
    .flatMap(extractConditionFields)
  const negated = extractConditionFields(node.not)
  const field = typeof node.field === 'string' ? [normalizeFactName(node.field)] : []
  return [...new Set([...nested, ...negated, ...field])]
}

function duplicateFamilyKey(rule: PolicyRuleItem) {
  const text = normalizeForReview(`${rule.rule_code} ${rule.name} ${rule.description}`)
  const fields = extractConditionFields(rule.rule_json?.condition).sort().join('|')

  if (text.includes('preapproval') || text.includes('pre approval') || text.includes('approval')) {
    return `approval:${fields}`
  }
  if (text.includes('receipt')) {
    const vehicleScope = text.includes('car') || text.includes('vehicle') || text.includes('parking') || text.includes('gas')
    return `${vehicleScope ? 'vehicle-' : ''}receipt:${fields}`
  }
  if (text.includes('alcohol')) {
    return `alcohol:${fields}`
  }
  if (text.includes('personal') || text.includes('named individual') || text.includes('cardholder')) {
    return `card-use:${fields}`
  }
  if (text.includes('ticket')) {
    return `ticket:${fields}`
  }

  return fields ? `condition:${fields}:${normalizeForReview(getOutcomeStatus(rule)).slice(0, 40)}` : null
}

function compareDuplicateRepresentatives(left: PolicyRuleItem, right: PolicyRuleItem) {
  const leftErrors = left.validation_errors.length > 0 ? 1 : 0
  const rightErrors = right.validation_errors.length > 0 ? 1 : 0
  if (leftErrors !== rightErrors) {
    return leftErrors - rightErrors
  }

  const leftConfidence = left.extraction_confidence ?? 0
  const rightConfidence = right.extraction_confidence ?? 0
  if (leftConfidence !== rightConfidence) {
    return rightConfidence - leftConfidence
  }

  return left.rule_code.localeCompare(right.rule_code)
}

function getRuleObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function getStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter((item): item is string => typeof item === 'string').map(normalizeFactName)
}

function hasScopedAppliesTo(appliesTo: Record<string, unknown>) {
  return ['business_categories', 'merchant_families', 'eligibility_tags', 'workflow_tags'].some((key) => {
    const value = appliesTo[key]
    return Array.isArray(value) && value.length > 0
  })
}

function isGlobalReceiptRule(text: string, hasCategoryOrMerchantScope: boolean) {
  return text.includes('receipt') && !hasCategoryOrMerchantScope
}

function isEvidenceOrHumanJudgmentField(field: string) {
  return EVIDENCE_OR_HUMAN_FIELDS.some((needle) => field.includes(needle))
}

function containsGuidanceOnlyLanguage(text: string) {
  return GUIDANCE_ONLY_TERMS.some((term) => text.includes(term))
}

function containsConductOnlyLanguage(text: string) {
  return CONDUCT_ONLY_TERMS.some((term) => text.includes(term))
}

function hasDirectConductEvidence(fields: Set<string>) {
  return ['is_personal_expense', 'is_fraudulent', 'is_falsified', 'named_cardholder_match', 'safety_incident_reported'].some(
    (field) => fields.has(field),
  )
}

function getOutcomeStatus(rule: PolicyRuleItem) {
  const outcome = getRuleObject(rule.rule_json?.outcome)
  if (typeof outcome.status === 'string') {
    return outcome.status
  }
  const violation = getRuleObject(outcome.violation)
  return typeof violation.status === 'string' ? violation.status : ''
}

function normalizeFactName(value: string) {
  return value.trim().toLowerCase()
}

function normalizeForReview(value: string) {
  return value.toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
}

function reviewSignalClassName(tone: ReviewSignalTone) {
  if (tone === 'blocker') {
    return 'bg-red-100 text-red-700 dark:bg-red-400/15 dark:text-red-100'
  }
  if (tone === 'positive') {
    return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-100'
  }
  return 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-100'
}

const BROAD_ACTIVITY_FIELDS = new Set([
  'debit_or_credit',
  'is_account_activity',
  'transaction_type',
  'transaction_status',
])

const CATEGORY_OR_MERCHANT_FIELDS = new Set([
  'business_category',
  'category',
  'category_code',
  'merchant',
  'merchant_category',
  'merchant_code',
  'merchant_dba_name',
  'merchant_family',
  'merchant_name',
  'mcc',
  'normalized_category',
  'normalized_merchant_family',
  'policy_category',
  'transaction_category',
])

const EVIDENCE_OR_HUMAN_FIELDS = [
  'approval',
  'attendee',
  'attachment',
  'business_purpose',
  'guest',
  'justification',
  'manager',
  'preapproval',
  'receipt',
]

const GUIDANCE_ONLY_TERMS = [
  'appropriate',
  'best effort',
  'discretion',
  'excessive',
  'reasonable',
  'unreasonable',
  'unusual',
]

const CONDUCT_ONLY_TERMS = [
  'abuse',
  'cardholder',
  'falsification',
  'falsified',
  'fraud',
  'impaired',
  'misconduct',
  'misrepresentation',
  'named individual',
  'personal use',
  'safety',
]

function formatRuleStatus(status: PolicyRuleStatus, t: ReturnType<typeof useUiPreferences>['t']) {
  const labels = {
    active: t('policyRules.active'),
    disabled: t('policyRules.disabledStatus'),
    draft: t('policyRules.draft'),
  } satisfies Record<PolicyRuleStatus, string>

  return labels[status]
}

function formatDocumentStatus(status: PolicyDocumentItem['extraction_status']) {
  const labels = {
    extracted: PAGE_COPY.documentExtracted,
    failed: PAGE_COPY.documentFailed,
    pending: PAGE_COPY.documentPending,
  } satisfies Record<PolicyDocumentItem['extraction_status'], string>

  return labels[status]
}

function formatRunStatus(
  status: NonNullable<PolicyRuleExtractionResponse['extraction_run']>['status'],
) {
  const labels = {
    completed: PAGE_COPY.runCompleted,
    failed: PAGE_COPY.runFailed,
    pending: PAGE_COPY.runPending,
  } satisfies Record<NonNullable<PolicyRuleExtractionResponse['extraction_run']>['status'], string>

  return labels[status]
}

function formatSourceType(sourceType: string) {
  const labels: Record<string, string> = {
    ai_extracted: PAGE_COPY.sourceAiExtracted,
    manual: PAGE_COPY.sourceManual,
    pasted_text: PAGE_COPY.sourcePastedText,
    seeded: PAGE_COPY.sourceSeeded,
    uploaded_pdf: PAGE_COPY.sourceUploadedPdf,
  }

  return labels[sourceType] ?? sourceType
}
