export function stableHash(input: string) {
  let hash = 2166136261

  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }

  return hash >>> 0
}

export function stableFingerprint(parts: Array<string | number | null | undefined>) {
  const normalized = parts.map((part) => String(part ?? '').trim().toUpperCase()).join('|')

  return stableHash(normalized).toString(16).padStart(8, '0')
}
