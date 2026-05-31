import type { ReactNode } from 'react'

type PageScaffoldProps = {
  title: string
  eyebrow: string
  description: string
  children?: ReactNode
}

export function PageScaffold({ children }: PageScaffoldProps) {
  return <section className="flex min-w-0 flex-col gap-5">{children}</section>
}
