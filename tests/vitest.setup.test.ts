import { describe, expect, it } from 'vitest'

describe('vitest setup', () => {
  it('runs deterministic unit tests without external services', () => {
    expect(1 + 1).toBe(2)
  })
})
