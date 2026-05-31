import { Languages, MoonStar, PanelLeftClose, PanelLeftOpen, ShieldCheck, Sun } from 'lucide-react'
import type { ReactNode } from 'react'

import { AssistantDock } from '@/components/assistant/AssistantDock'
import { AmbientBackdrop } from '@/components/experience/AmbientBackdrop'
import { Button } from '@/components/ui/button'
import { useUiPreferences, type TranslationKey } from '@/lib/ui/preferences'
import { cn } from '@/lib/utils'
import { routes, type AppRouteId } from '@/routes/routes'

type AppShellProps = {
  activeRouteId: AppRouteId
  children: ReactNode
  onNavigate: (path: string) => void
}

function getRouteLabel(routeId: AppRouteId, fallback: string, language: 'en' | 'fr') {
  if (routeId === 'compliance') {
    return language === 'fr' ? 'Revues' : 'Reviews'
  }

  return fallback
}

export function AppShell({ activeRouteId, children, onNavigate }: AppShellProps) {
  const activeRoute = routes.find((route) => route.id === activeRouteId) ?? routes[0]
  const { language, sidebarCollapsed, t, themeMode, toggleLanguage, toggleSidebarCollapsed, toggleThemeMode } = useUiPreferences()
  const activeRouteLabel = getRouteLabel(activeRoute.id, activeRoute.label, language)
  const activeRouteDescription = t(`routes.${activeRoute.id}.description` as TranslationKey)
  const sidebarToggleLabel = sidebarCollapsed ? t('shell.expandSidebar') : t('shell.collapseSidebar')
  const contentWidthClass = activeRouteId === 'talkToData' ? 'max-w-none' : 'max-w-[1280px]'

  return (
    <div className="bank-shell min-h-svh text-foreground lg:h-svh lg:overflow-hidden">
      <AmbientBackdrop />

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 hidden border-r border-sidebar-border bg-sidebar/86 text-sidebar-foreground backdrop-blur-2xl transition-[width] duration-300 lg:flex lg:flex-col',
          sidebarCollapsed ? 'w-20' : 'w-72',
        )}
      >
        <div className={cn('flex h-20 items-center border-b border-sidebar-border px-5', sidebarCollapsed ? 'justify-center' : 'gap-3')}>
          <div className="relative flex size-10 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-lg shadow-black/20">
            <span className="absolute inset-0 rounded-lg bg-white/10 blur-sm" />
            <ShieldCheck className="size-5" aria-hidden="true" />
          </div>
          <div className={cn('min-w-0', sidebarCollapsed && 'hidden')}>
            <p className="truncate text-sm font-semibold">{t('app.name')}</p>
            <p className="truncate text-xs text-sidebar-foreground/65">{t('app.subtitle')}</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1.5 p-3" aria-label="Primary navigation">
          {routes.map((route) => {
            const Icon = route.icon
            const isActive = route.id === activeRouteId
            const label = getRouteLabel(route.id, route.label, language)

            return (
              <button
                key={route.id}
                type="button"
                onClick={() => onNavigate(route.path)}
                className={cn(
                  'nav-pill group flex w-full items-center rounded-lg px-3 py-2.5 text-left text-sm font-medium',
                  sidebarCollapsed ? 'justify-center' : 'gap-3',
                  isActive ? 'nav-pill-active bg-sidebar-primary text-sidebar-primary-foreground shadow-md shadow-black/15' : 'text-sidebar-foreground/72',
                )}
                aria-current={isActive ? 'page' : undefined}
                aria-label={label}
                title={sidebarCollapsed ? label : undefined}
              >
                <Icon
                  className={cn(
                    'size-4 transition-transform duration-200 ease-out',
                    isActive ? 'scale-100' : 'group-hover:scale-105 group-hover:-translate-y-px',
                  )}
                  aria-hidden="true"
                />
                {!sidebarCollapsed ? <span>{label}</span> : null}
              </button>
            )
          })}
        </nav>
      </aside>

      <div className={cn('relative z-10 lg:flex lg:h-svh lg:min-h-0 lg:flex-col', sidebarCollapsed ? 'lg:pl-20' : 'lg:pl-72')}>
        <header className="sticky top-0 z-20 border-b border-border/80 bg-background/72 backdrop-blur-2xl lg:shrink-0">
          <div className="flex min-h-16 items-center justify-between gap-3 px-4 lg:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                onClick={toggleSidebarCollapsed}
                aria-label={sidebarToggleLabel}
                title={sidebarToggleLabel}
                className="hidden lg:inline-flex"
              >
                {sidebarCollapsed ? <PanelLeftOpen className="size-4" aria-hidden="true" /> : <PanelLeftClose className="size-4" aria-hidden="true" />}
              </Button>

              <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">{activeRouteLabel}</p>
              <p className="hidden text-sm text-muted-foreground lg:block">{activeRouteDescription}</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={toggleLanguage}
                aria-label={t('shell.switchLanguage')}
              >
                <Languages className="size-4" aria-hidden="true" />
                <span>{t('shell.language')}</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                onClick={toggleThemeMode}
                aria-label={t('shell.switchTheme')}
                title={themeMode === 'light' ? t('shell.themeDark') : t('shell.themeLight')}
              >
                {themeMode === 'light' ? (
                  <MoonStar className="size-4" aria-hidden="true" />
                ) : (
                  <Sun className="size-4" aria-hidden="true" />
                )}
              </Button>
            </div>
          </div>

          <nav className="hide-scrollbar flex gap-2 overflow-x-auto border-t border-border/70 px-4 py-2 lg:hidden" aria-label="Mobile navigation">
            {routes.map((route) => {
              const Icon = route.icon
              const isActive = route.id === activeRouteId
              const label = getRouteLabel(route.id, route.label, language)

              return (
                <button
                  key={route.id}
                  type="button"
                  onClick={() => onNavigate(route.path)}
                  className={cn(
                    'nav-pill-mobile group inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium',
                    isActive ? 'nav-pill-mobile-active bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                  )}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon
                    className={cn(
                      'size-4 transition-transform duration-200 ease-out',
                      isActive ? 'scale-100' : 'group-hover:scale-105 group-hover:-translate-y-px',
                    )}
                    aria-hidden="true"
                  />
                  {label}
                </button>
              )
            })}
          </nav>
        </header>

        <main className="desktop-scroll px-4 py-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overflow-x-hidden lg:px-6 lg:py-5">
          <div className={cn('mx-auto min-w-0', contentWidthClass)}>{children}</div>
        </main>
      </div>

      <AssistantDock onNavigate={onNavigate} />
    </div>
  )
}
