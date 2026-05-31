import type { AppRouteId } from '@/routes/routes'

export type AssistantContextEntity = {
  type: string
  id?: string | null
  label: string
  status?: string | null
  attributes?: Record<string, unknown>
}

export type AssistantContextArtifact = {
  type: string
  id?: string | null
  label: string
  status?: string | null
  metadata?: Record<string, unknown>
}

export type AssistantPageContext = {
  routeId: AppRouteId
  title: string
  summary: string
  filters?: Record<string, unknown>
  details?: Record<string, unknown>
  metrics?: Record<string, unknown>
  focus?: AssistantContextEntity | null
  focusEntities?: AssistantContextEntity[]
  visibleEntities?: AssistantContextEntity[]
  artifacts?: AssistantContextArtifact[]
  availableViews?: string[]
  suggestions?: string[]
}

export type AssistantConversationTurn = {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  createdAt: string | null
  result: import('@/lib/api/backendClient').InsightQueryResponse | null
}
