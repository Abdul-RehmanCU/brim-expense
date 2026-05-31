import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AssistantProvider } from '@/lib/assistant/AssistantProvider'
import { UiPreferencesProvider } from '@/lib/ui/UiPreferencesProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <UiPreferencesProvider>
      <AssistantProvider>
        <App />
      </AssistantProvider>
    </UiPreferencesProvider>
  </StrictMode>,
)
