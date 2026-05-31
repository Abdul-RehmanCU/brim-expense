import { useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  UiPreferencesContext,
  dictionaries,
  getStoredLanguage,
  getStoredSidebarCollapsed,
  getStoredThemeMode,
  localeByLanguage,
  uiStorageKeys,
  type Language,
  type ThemeMode,
  type UiPreferencesContextValue,
} from '@/lib/ui/preferences'

export function UiPreferencesProvider({ children }: { children: ReactNode }) {
  const [themeMode, setThemeMode] = useState<ThemeMode>(getStoredThemeMode)
  const [language, setLanguage] = useState<Language>(getStoredLanguage)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(getStoredSidebarCollapsed)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', themeMode === 'dark')
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(uiStorageKeys.themeMode, themeMode)
  }, [themeMode])

  useEffect(() => {
    document.documentElement.lang = language === 'fr' ? 'fr-CA' : 'en-CA'
    window.localStorage.setItem(uiStorageKeys.language, language)
  }, [language])

  useEffect(() => {
    window.localStorage.setItem(uiStorageKeys.sidebarCollapsed, String(sidebarCollapsed))
  }, [sidebarCollapsed])

  const value = useMemo<UiPreferencesContextValue>(() => {
    const dictionary = dictionaries[language]

    return {
      language,
      locale: localeByLanguage[language],
      setSidebarCollapsed,
      setLanguage,
      setThemeMode,
      sidebarCollapsed,
      t: (key) => dictionary[key],
      themeMode,
      toggleSidebarCollapsed: () => setSidebarCollapsed((currentValue) => !currentValue),
      toggleLanguage: () => setLanguage((currentLanguage) => (currentLanguage === 'en' ? 'fr' : 'en')),
      toggleThemeMode: () => setThemeMode((currentThemeMode) => (currentThemeMode === 'light' ? 'dark' : 'light')),
    }
  }, [language, sidebarCollapsed, themeMode])

  return <UiPreferencesContext.Provider value={value}>{children}</UiPreferencesContext.Provider>
}
