import { ChevronDown, Expand, Minimize2, Plus, Send, X } from 'lucide-react'

import { PolyAvatar } from '@/components/assistant/PolyAvatar'
import { Button } from '@/components/ui/button'
import { useAssistant } from '@/lib/assistant/AssistantProvider'
import { cn } from '@/lib/utils'

type AssistantDockProps = {
  onNavigate: (path: string) => void
}

export function AssistantDock({ onNavigate }: AssistantDockProps) {
  const {
    question,
    setQuestion,
    session,
    sessions,
    conversation,
    selectedResult,
    isAsking,
    isLoadingSession,
    error,
    dockState,
    pageContext,
    askQuestion,
    selectSession,
    openDock,
    closeDock,
    expandDock,
    collapseDock,
    clearError,
    startNewSession,
  } = useAssistant()
  if (pageContext?.routeId === 'talkToData') {
    return null
  }

  if (dockState === 'closed') {
    return (
      <button
        type="button"
        onClick={openDock}
        className="fixed right-4 bottom-4 z-40 inline-flex items-center gap-3 rounded-full border border-border/70 bg-card/92 px-4 py-3 text-left shadow-2xl shadow-black/25 backdrop-blur-xl transition hover:border-primary/40 hover:shadow-primary/10 lg:right-6 lg:bottom-6"
      >
        <PolyAvatar className="size-10 rounded-full ring-2 ring-primary/15" />
        <span className="hidden min-w-0 lg:block">
          <span className="block text-sm font-semibold text-foreground">Ask Poly</span>
          <span className="block max-w-52 truncate text-xs text-muted-foreground">
            {pageContext?.title ? `Using ${pageContext.title.toLowerCase()} context` : 'Open the assistant'}
          </span>
        </span>
      </button>
    )
  }

  const isExpanded = dockState === 'expanded'
  const visibleConversation = isExpanded ? conversation : conversation.slice(-8)
  const recentSessions = sessions.filter((entry) => entry.id !== session?.id).slice(0, isExpanded ? 5 : 2)
  return (
    <section
      className={cn(
        'fixed right-4 bottom-4 z-40 flex flex-col overflow-hidden rounded-3xl border border-border/70 bg-card/96 shadow-2xl shadow-black/30 backdrop-blur-2xl transition-all lg:right-6 lg:bottom-6',
        isExpanded ? 'h-[min(84vh,56rem)] w-[min(calc(100vw-2rem),58rem)]' : 'h-[min(78vh,44rem)] w-[min(calc(100vw-2rem),32rem)]',
      )}
    >
      <header className="flex items-start justify-between gap-4 border-b border-border/70 px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <PolyAvatar className="size-11 rounded-2xl ring-2 ring-primary/15" />
            <div className="min-w-0">
              <p className="text-base font-semibold text-foreground">Poly</p>
              <p className="truncate text-sm text-muted-foreground">
                {pageContext?.title ? `Using ${pageContext.title.toLowerCase()} context` : 'PolyPilot finance copilot'}
              </p>
            </div>
          </div>
          {!isExpanded && session ? <p className="mt-2 truncate text-sm text-muted-foreground">{session.title}</p> : null}
        </div>

        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="icon-sm" onClick={startNewSession} aria-label="Start a new session">
            <Plus className="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              if (isExpanded) {
                collapseDock()
              } else {
                expandDock()
              }
            }}
            aria-label={isExpanded ? 'Collapse assistant' : 'Expand assistant'}
          >
            {isExpanded ? <Minimize2 className="size-4" aria-hidden="true" /> : <Expand className="size-4" aria-hidden="true" />}
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" onClick={closeDock} aria-label="Close assistant">
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {isExpanded ? (
          <aside className="hidden w-72 shrink-0 border-r border-border/70 bg-background/45 md:flex md:flex-col">
            <div className="border-b border-border/70 px-4 py-4">
              <Button type="button" className="w-full justify-start" onClick={startNewSession}>
                <Plus className="size-4" aria-hidden="true" />
                New chat
              </Button>
              {pageContext?.summary ? <p className="mt-3 text-sm leading-6 text-muted-foreground">{pageContext.summary}</p> : null}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              {selectedResult ? (
                <div className="rounded-2xl border border-primary/20 bg-primary/6 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Latest answer</p>
                  <p className="mt-2 text-sm leading-6 text-foreground">{selectedResult.summary}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="status-chip bg-muted text-muted-foreground">{selectedResult.plan.tool}</span>
                    <span className="status-chip bg-muted text-muted-foreground">{selectedResult.visualization ?? 'table'}</span>
                    <span className="status-chip bg-muted text-muted-foreground">{selectedResult.rows.length} rows</span>
                  </div>
                </div>
              ) : null}

              <div className={cn('space-y-3', selectedResult ? 'mt-4' : '')}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Chats</p>
                  {session ? <span className="truncate text-xs text-muted-foreground">Current: {session.title}</span> : null}
                </div>

                {session ? (
                  <button
                    type="button"
                    className="w-full rounded-2xl border border-primary/25 bg-primary/8 px-3 py-3 text-left transition hover:border-primary/45"
                    onClick={() => void selectSession(session.id)}
                    disabled={isLoadingSession}
                  >
                    <p className="text-sm font-medium text-foreground">{session.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">Current conversation</p>
                  </button>
                ) : null}

                {recentSessions.length > 0 ? (
                  <div className="space-y-2">
                    {recentSessions.map((entry) => (
                      <button
                        key={entry.id}
                        type="button"
                        className="w-full rounded-2xl border border-border/80 bg-card/65 px-3 py-3 text-left transition hover:border-primary/40 hover:bg-background"
                        onClick={() => void selectSession(entry.id)}
                        disabled={isLoadingSession}
                      >
                        <p className="truncate text-sm font-medium text-foreground">{entry.title}</p>
                        <p className="mt-1 text-xs text-muted-foreground">Open recent chat</p>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-card/50 px-3 py-4 text-sm text-muted-foreground">
                    Your recent chats will show up here.
                  </div>
                )}
              </div>
            </div>

            <div className="border-t border-border/70 px-4 py-4">
              <button
                type="button"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary transition hover:text-primary/80"
                onClick={() => onNavigate('/talk-to-data')}
              >
                Open full workspace
                <ChevronDown className="size-3.5 -rotate-90" aria-hidden="true" />
              </button>
            </div>
          </aside>
        ) : null}

        <div className="flex min-h-0 flex-1 flex-col">
          {!isExpanded ? (
            <div className="flex items-center justify-between gap-3 border-b border-border/70 px-5 py-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Chat</p>
                <p className="truncate text-sm text-muted-foreground">
                  {pageContext?.focus?.label ? `Focused on ${pageContext.focus.label}` : 'Ask about the page you are viewing'}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <Button type="button" variant="ghost" size="sm" onClick={startNewSession}>
                  <Plus className="size-4" aria-hidden="true" />
                  New
                </Button>
                <button
                  type="button"
                  className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary transition hover:text-primary/80"
                  onClick={() => onNavigate('/talk-to-data')}
                >
                  Open page
                  <ChevronDown className="size-3.5 -rotate-90" aria-hidden="true" />
                </button>
              </div>
            </div>
          ) : null}

          {error ? (
            <div className="border-b border-border/70 px-5 py-3">
              <div className="rounded-lg border border-red-300/70 bg-red-100/70 p-3 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">
                <div className="flex items-start justify-between gap-3">
                  <span>{error}</span>
                  <button type="button" className="text-xs font-medium" onClick={clearError}>
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {visibleConversation.length > 0 ? (
              <div className="space-y-3">
                {visibleConversation.map((turn) => (
                  <article
                    key={turn.id}
                    className={cn(
                      'max-w-[94%] whitespace-pre-wrap rounded-3xl px-4 py-3 text-sm leading-7',
                      turn.role === 'user'
                        ? 'ml-auto bg-primary text-primary-foreground shadow-sm'
                        : 'border border-border/70 bg-background text-foreground',
                    )}
                  >
                    <p>{turn.content}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="flex h-full min-h-52 items-center">
                <div className="w-full rounded-2xl border border-dashed border-border/70 bg-background/55 p-5">
                  <p className="text-sm font-medium text-foreground">Start a conversation from anywhere in the app.</p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    Ask for summaries, next steps, or a quick explanation of the records you are looking at.
                  </p>
                </div>
              </div>
            )}
          </div>

          <form
            className="border-t border-border/70 px-5 py-4"
            onSubmit={(event) => {
              event.preventDefault()
              void askQuestion()
            }}
          >
            <textarea
              className="min-h-36 w-full resize-none rounded-2xl border border-input bg-background px-4 py-3 text-sm leading-7 text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={
                pageContext?.title
                  ? `Ask about ${pageContext.title.toLowerCase()}, next steps, or anything unclear`
                  : 'Ask about spend, approvals, policy issues, or next steps'
              }
            />
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">
                  {pageContext?.focus?.label ? `Focused on ${pageContext.focus.label}` : 'No item selected'}
                </p>
              </div>
              <Button type="submit" disabled={isAsking || !question.trim()} className="sm:self-end">
                <Send className={cn('size-4', isAsking && 'animate-pulse')} aria-hidden="true" />
                {isAsking ? 'Thinking...' : 'Ask'}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </section>
  )
}
