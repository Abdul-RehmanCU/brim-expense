/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  createInsightSession,
  getInsightSession,
  listInsightSessions,
  queryInsights,
  type InsightChatMessage,
  type InsightCitation,
  type InsightPlan,
  type InsightPlannerSource,
  type InsightQueryResponse,
  type InsightResultRow,
  type InsightSession,
  type InsightValidationResult,
} from '@/lib/api/backendClient'
import type { AssistantConversationTurn, AssistantPageContext } from '@/lib/assistant/types'

const TALK_TO_DATA_SESSION_KEY = 'brim-talk-to-data-session-id'

type AssistantDockState = 'closed' | 'open' | 'expanded'

type AssistantContextValue = {
  question: string
  setQuestion: (value: string) => void
  session: InsightSession | null
  sessions: InsightSession[]
  conversation: AssistantConversationTurn[]
  selectedAssistantTurnId: string | null
  selectedResult: InsightQueryResponse | null
  isAsking: boolean
  isLoadingSession: boolean
  error: string | null
  dockState: AssistantDockState
  pageContext: AssistantPageContext | null
  setPageContext: (context: AssistantPageContext | null) => void
  setSelectedAssistantTurnId: (id: string | null) => void
  askQuestion: (nextQuestion?: string) => Promise<void>
  selectSession: (sessionId: string) => Promise<void>
  openDock: () => void
  closeDock: () => void
  expandDock: () => void
  collapseDock: () => void
  clearError: () => void
  startNewSession: () => void
}

const AssistantContext = createContext<AssistantContextValue | null>(null)

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [question, setQuestion] = useState('')
  const [session, setSession] = useState<InsightSession | null>(null)
  const [sessions, setSessions] = useState<InsightSession[]>([])
  const [conversation, setConversation] = useState<AssistantConversationTurn[]>([])
  const [selectedAssistantTurnId, setSelectedAssistantTurnId] = useState<string | null>(null)
  const [isAsking, setIsAsking] = useState(false)
  const [isLoadingSession, setIsLoadingSession] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dockState, setDockState] = useState<AssistantDockState>('closed')
  const [pageContext, setPageContext] = useState<AssistantPageContext | null>(null)
  const [lastExternalPageContext, setLastExternalPageContext] = useState<AssistantPageContext | null>(null)

  const selectedResult = useMemo(
    () => conversation.find((turn) => turn.id === selectedAssistantTurnId && turn.role === 'assistant')?.result ?? null,
    [conversation, selectedAssistantTurnId],
  )

  useEffect(() => {
    let isMounted = true

    async function loadExistingSession() {
      try {
        const availableSessions = await listInsightSessions()
        if (isMounted) {
          setSessions(availableSessions)
        }
      } catch {
        // Ignore session list loading errors during bootstrap.
      }

      const savedSessionId = window.localStorage.getItem(TALK_TO_DATA_SESSION_KEY)
      if (!savedSessionId) {
        if (isMounted) {
          setIsLoadingSession(false)
        }
        return
      }

      try {
        const detail = await getInsightSession(savedSessionId)
        if (!isMounted) {
          return
        }

        const loadedConversation = detail.messages.map(mapMessageToConversationTurn)
        setSession(detail.session)
        setConversation(loadedConversation)
        setSelectedAssistantTurnId(pickLatestAssistantTurnId(loadedConversation))
      } catch {
        window.localStorage.removeItem(TALK_TO_DATA_SESSION_KEY)
      } finally {
        if (isMounted) {
          setIsLoadingSession(false)
        }
      }
    }

    void loadExistingSession()

    return () => {
      isMounted = false
    }
  }, [])

  async function refreshSessions(preferredSessionId?: string) {
    const availableSessions = await listInsightSessions()
    setSessions(availableSessions)
    if (preferredSessionId && !availableSessions.some((entry) => entry.id === preferredSessionId)) {
      window.localStorage.removeItem(TALK_TO_DATA_SESSION_KEY)
    }
  }

  async function loadSession(sessionId: string) {
    setIsLoadingSession(true)
    setError(null)
    try {
      const detail = await getInsightSession(sessionId)
      const loadedConversation = detail.messages.map(mapMessageToConversationTurn)
      window.localStorage.setItem(TALK_TO_DATA_SESSION_KEY, detail.session.id)
      setSession(detail.session)
      setConversation(loadedConversation)
      setSelectedAssistantTurnId(pickLatestAssistantTurnId(loadedConversation))
    } catch (sessionError) {
      window.localStorage.removeItem(TALK_TO_DATA_SESSION_KEY)
      setError(sessionError instanceof Error ? sessionError.message : 'Could not load this chat.')
    } finally {
      setIsLoadingSession(false)
    }
  }

  async function ensureSession(initialQuestion?: string) {
    if (session) {
      return session.id
    }

    const detail = await createInsightSession({
      initial_question: initialQuestion?.trim() || undefined,
      page_context: serializePageContext(pageContext, lastExternalPageContext),
    })

    window.localStorage.setItem(TALK_TO_DATA_SESSION_KEY, detail.session.id)
    setSession(detail.session)
    setSessions((current) => [detail.session, ...current.filter((entry) => entry.id !== detail.session.id)])

    const loadedConversation = detail.messages.map(mapMessageToConversationTurn)
    setConversation(loadedConversation)
    setSelectedAssistantTurnId(pickLatestAssistantTurnId(loadedConversation))

    return detail.session.id
  }

  async function askQuestion(nextQuestion = question) {
    const trimmedQuestion = nextQuestion.trim()
    if (!trimmedQuestion) {
      return
    }

    setIsAsking(true)
    setError(null)
    setDockState((current) => (current === 'closed' ? 'open' : current))
    setSelectedAssistantTurnId(null)

    try {
      const sessionId = await ensureSession(trimmedQuestion)
      const response = await queryInsights({
        question: trimmedQuestion,
        session_id: sessionId,
        page_context: serializePageContext(pageContext, lastExternalPageContext),
      })
      const nextConversation = appendExchange(conversation, trimmedQuestion, response)

      if (response.session_id && response.session_id !== sessionId) {
        window.localStorage.setItem(TALK_TO_DATA_SESSION_KEY, response.session_id)
      }

      setQuestion('')
      setConversation(nextConversation)
      setSelectedAssistantTurnId(pickLatestAssistantTurnId(nextConversation))
      void refreshSessions(response.session_id ?? sessionId).catch(() => undefined)
    } catch (queryError) {
      setError(queryError instanceof Error ? queryError.message : 'Could not query the insight agent.')
    } finally {
      setIsAsking(false)
    }
  }

  async function selectSession(sessionId: string) {
    if (session?.id === sessionId) {
      return
    }
    await loadSession(sessionId)
  }

  function openDock() {
    setDockState('open')
  }

  function closeDock() {
    setDockState('closed')
  }

  function expandDock() {
    setDockState('expanded')
  }

  function collapseDock() {
    setDockState('open')
  }

  function clearError() {
    setError(null)
  }

  function startNewSession() {
    window.localStorage.removeItem(TALK_TO_DATA_SESSION_KEY)
    setSession(null)
    setConversation([])
    setSelectedAssistantTurnId(null)
    setQuestion('')
    setError(null)
  }

  const value: AssistantContextValue = {
    question,
    setQuestion,
    session,
    sessions,
    conversation,
    selectedAssistantTurnId,
    selectedResult,
    isAsking,
    isLoadingSession,
    error,
    dockState,
    pageContext,
    setPageContext: (context) => {
      setPageContext(context)
      if (context && context.routeId !== 'talkToData') {
        setLastExternalPageContext(context)
      }
    },
    setSelectedAssistantTurnId,
    askQuestion,
    selectSession,
    openDock,
    closeDock,
    expandDock,
    collapseDock,
    clearError,
    startNewSession,
  }

  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>
}

export function useAssistant() {
  const context = useContext(AssistantContext)
  if (!context) {
    throw new Error('useAssistant must be used within an AssistantProvider.')
  }
  return context
}

export function useAssistantPageContext(context: AssistantPageContext) {
  const { setPageContext } = useAssistant()

  useEffect(() => {
    setPageContext(context)
    return () => {
      setPageContext(null)
    }
  }, [context, setPageContext])
}

function serializePageContext(pageContext: AssistantPageContext | null, fallbackContext: AssistantPageContext | null = null) {
  const contextToSerialize = pageContext

  if (!contextToSerialize) {
    return null
  }

  const focusEntities =
    contextToSerialize.focusEntities && contextToSerialize.focusEntities.length > 0
      ? contextToSerialize.focusEntities
      : contextToSerialize.focus
        ? [contextToSerialize.focus]
        : []

  const payload: Record<string, unknown> = {
    route_id: contextToSerialize.routeId,
    summary: contextToSerialize.summary,
    filters: contextToSerialize.filters ?? {},
    metrics: contextToSerialize.metrics ?? {},
    focus: contextToSerialize.focus ?? null,
    focus_entities: focusEntities,
    visible_entities: contextToSerialize.visibleEntities ?? [],
    artifacts: contextToSerialize.artifacts ?? [],
    available_views: contextToSerialize.availableViews ?? [],
    suggestions: contextToSerialize.suggestions ?? [],
  }

  if (contextToSerialize.details) {
    payload.details = contextToSerialize.details
  }

  if (contextToSerialize.routeId === 'talkToData' && fallbackContext) {
    payload.related_context = {
      page: fallbackContext.title,
      route: fallbackContext.routeId,
      summary: fallbackContext.summary,
      filters: fallbackContext.filters ?? {},
      metrics: fallbackContext.metrics ?? {},
      focus: fallbackContext.focus ?? null,
    }
  }

  return {
    page: contextToSerialize.title,
    route: contextToSerialize.routeId,
    payload,
  }
}

function appendExchange(conversation: AssistantConversationTurn[], nextQuestion: string, response: InsightQueryResponse) {
  const userTurn: AssistantConversationTurn = {
    id: `user-${crypto.randomUUID()}`,
    role: 'user',
    content: nextQuestion,
    createdAt: new Date().toISOString(),
    result: null,
  }

  const assistantTurn: AssistantConversationTurn = {
    id: `assistant-${crypto.randomUUID()}`,
    role: 'assistant',
    content: response.summary,
    createdAt: new Date().toISOString(),
    result: response,
  }

  return [...conversation, userTurn, assistantTurn]
}

function pickLatestAssistantTurnId(conversation: AssistantConversationTurn[]) {
  return [...conversation].reverse().find((turn) => turn.role === 'assistant' && turn.result)?.id ?? null
}

function mapMessageToConversationTurn(message: InsightChatMessage): AssistantConversationTurn {
  const metadata = isRecord(message.metadata) ? message.metadata : {}
  const result = message.role === 'assistant' ? buildResultFromMessage(message.content, metadata) : null

  return {
    id: message.id ?? `${message.role}-${message.created_at ?? crypto.randomUUID()}`,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    result,
  }
}

function buildResultFromMessage(summary: string, metadata: Record<string, unknown>): InsightQueryResponse | null {
  if (metadata.kind !== 'insight_response') {
    return null
  }

  const plan = metadata.plan
  const validation = normalizeValidation(metadata.validation)
  if (!isInsightPlan(plan) || !validation) {
    return null
  }

  return {
    question: typeof metadata.question === 'string' ? metadata.question : '',
    session_id: typeof metadata.session_id === 'string' ? metadata.session_id : null,
    plan,
    validation,
    planner_source: normalizePlannerSource(metadata.planner_source),
    summary,
    columns: Array.isArray(metadata.columns) ? metadata.columns.filter((column): column is string => typeof column === 'string') : [],
    rows: normalizeRows(metadata.rows),
    citations: normalizeCitations(metadata.citations),
    visualization: typeof metadata.visualization === 'string' ? metadata.visualization : null,
    metadata: isRecord(metadata.metadata) ? metadata.metadata : {},
  }
}

function normalizeValidation(value: unknown): InsightValidationResult | null {
  if (!isRecord(value) || typeof value.valid !== 'boolean') {
    return null
  }

  return {
    valid: value.valid,
    errors: Array.isArray(value.errors) ? value.errors.filter((entry): entry is string => typeof entry === 'string') : [],
    warnings: Array.isArray(value.warnings) ? value.warnings.filter((entry): entry is string => typeof entry === 'string') : [],
  }
}

function normalizeRows(value: unknown): InsightResultRow[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((row) => {
    if (!isRecord(row) || typeof row.label !== 'string' || !isRecord(row.values)) {
      return []
    }
    return [{ label: row.label, values: row.values }]
  })
}

function normalizeCitations(value: unknown): InsightCitation[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((citation) => {
    if (!isRecord(citation) || typeof citation.text !== 'string') {
      return []
    }

    return [
      {
        rule_code: typeof citation.rule_code === 'string' ? citation.rule_code : null,
        clause_id: typeof citation.clause_id === 'string' ? citation.clause_id : null,
        title: typeof citation.title === 'string' ? citation.title : null,
        text: citation.text,
        source: typeof citation.source === 'string' ? citation.source : null,
        match_score: typeof citation.match_score === 'number' ? citation.match_score : null,
      },
    ]
  })
}

function normalizePlannerSource(value: unknown): InsightPlannerSource {
  return value === 'deterministic_followup' || value === 'anthropic_structured' || value === 'claude_fallback' ? value : 'deterministic'
}

function isInsightPlan(value: unknown): value is InsightPlan {
  return (
    isRecord(value) &&
    typeof value.intent === 'string' &&
    typeof value.mode === 'string' &&
    typeof value.tool === 'string' &&
    isRecord(value.filters) &&
    Array.isArray(value.group_by) &&
    Array.isArray(value.metrics) &&
    Array.isArray(value.sort) &&
    typeof value.limit === 'number' &&
    (typeof value.visualization === 'string' || value.visualization === null) &&
    isRecord(value.comparison_options) &&
    isRecord(value.report_options)
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
