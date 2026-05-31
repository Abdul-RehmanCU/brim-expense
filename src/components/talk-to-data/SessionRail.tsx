import { Loader2, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { InsightSession } from '@/lib/api/backendClient'

const DEFAULT_VISIBLE_SESSIONS = 4

type SessionRailProps = {
  sessions: InsightSession[]
  activeSessionId: string | null
  isLoading: boolean
  onSelectSession: (sessionId: string) => void
  onStartNewChat: () => void
}

export function SessionRail({
  sessions,
  activeSessionId,
  isLoading,
  onSelectSession,
  onStartNewChat,
}: SessionRailProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const hasOverflow = sessions.length > DEFAULT_VISIBLE_SESSIONS

  const visibleSessions = useMemo(() => {
    if (isExpanded || !hasOverflow) {
      return sessions
    }

    const defaultSessions = sessions.slice(0, DEFAULT_VISIBLE_SESSIONS)
    if (!activeSessionId || defaultSessions.some((entry) => entry.id === activeSessionId)) {
      return defaultSessions
    }

    const activeSession = sessions.find((entry) => entry.id === activeSessionId)
    if (!activeSession) {
      return defaultSessions
    }

    return [...sessions.slice(0, DEFAULT_VISIBLE_SESSIONS - 1), activeSession]
  }, [activeSessionId, hasOverflow, isExpanded, sessions])

  const hiddenCount = Math.max(sessions.length - visibleSessions.length, 0)

  return (
    <aside className="surface-panel flex min-h-[82vh] flex-col overflow-hidden">
      <div className="border-b border-border/70 px-5 py-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-base font-semibold text-foreground">Chats</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">Pick up older threads or start a clean one.</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={onStartNewChat}>
            <Plus className="size-4" aria-hidden="true" />
            New
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isLoading ? (
          <div className="flex items-center gap-2 rounded-2xl border border-border/70 bg-background/60 px-4 py-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Loading chats...
          </div>
        ) : sessions.length > 0 ? (
          <div className="space-y-3">
            {visibleSessions.map((entry) => {
              const isActive = entry.id === activeSessionId
              return (
                <button
                  key={entry.id}
                  type="button"
                  className={`w-full rounded-3xl border px-4 py-4 text-left transition ${
                    isActive
                      ? 'border-primary/60 bg-primary/8 text-foreground'
                      : 'border-border/70 bg-background/60 text-foreground hover:border-primary/40'
                  }`}
                  onClick={() => onSelectSession(entry.id)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="line-clamp-2 text-sm font-medium leading-6">{entry.title}</p>
                    {isActive ? <span className="status-chip bg-primary/10 text-primary">Open</span> : null}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{formatSessionTimestamp(entry.updated_at ?? entry.created_at)}</p>
                </button>
              )
            })}

            {hasOverflow ? (
              <button
                type="button"
                className="w-full rounded-2xl border border-dashed border-border/70 bg-background/40 px-4 py-3 text-sm font-medium text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
                onClick={() => setIsExpanded((current) => !current)}
              >
                {isExpanded ? 'Show less' : `Show more${hiddenCount > 0 ? ` (${hiddenCount})` : ''}`}
              </button>
            ) : null}
          </div>
        ) : (
          <div className="rounded-3xl border border-dashed border-border/70 bg-background/55 p-5 text-sm leading-6 text-muted-foreground">
            No saved chats yet. Start one and it will show up here.
          </div>
        )}
      </div>
    </aside>
  )
}

function formatSessionTimestamp(value: string | null) {
  if (!value) {
    return 'No activity yet'
  }

  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) {
    return value
  }

  return timestamp.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
