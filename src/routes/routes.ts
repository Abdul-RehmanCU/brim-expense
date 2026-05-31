import {
  BadgeCheck,
  BarChart3,
  Bot,
  FileSpreadsheet,
  Inbox,
  Landmark,
  ListChecks,
  Upload,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export type AppRouteId =
  | 'dashboard'
  | 'import'
  | 'talkToData'
  | 'transactions'
  | 'compliance'
  | 'approvals'
  | 'reports'
  | 'policyRules'

export type AppRoute = {
  id: AppRouteId
  label: string
  path: string
  description: string
  icon: LucideIcon
}

export const routes: AppRoute[] = [
  {
    id: 'dashboard',
    label: 'Overview',
    path: '/dashboard',
    description: 'See what was imported and what needs attention.',
    icon: BarChart3,
  },
  {
    id: 'import',
    label: 'Import',
    path: '/import',
    description: 'Bring in a card export and preview the cleanup.',
    icon: Upload,
  },
  {
    id: 'policyRules',
    label: 'Policy Setup',
    path: '/policy-rules',
    description: 'Manage the rules behind your review flow.',
    icon: Landmark,
  },
  {
    id: 'transactions',
    label: 'Transactions',
    path: '/transactions',
    description: 'Browse the cleaned and mapped transactions.',
    icon: Inbox,
  },
  {
    id: 'compliance',
    label: 'Reviews',
    path: '/compliance',
    description: 'See which transactions need a closer look.',
    icon: BadgeCheck,
  },
  {
    id: 'approvals',
    label: 'Approvals',
    path: '/approvals',
    description: 'Work through decisions waiting on a manager.',
    icon: ListChecks,
  },
  {
    id: 'reports',
    label: 'Reports',
    path: '/reports',
    description: 'Create and export report packages.',
    icon: FileSpreadsheet,
  },
  {
    id: 'talkToData',
    label: 'Ask',
    path: '/talk-to-data',
    description: 'Ask plain-language questions about spend.',
    icon: Bot,
  },
]

export function getRouteByPath(path: string): AppRoute {
  return routes.find((route) => route.path === path) ?? routes[0]
}
