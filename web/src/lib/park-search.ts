export const MIN_NAME_QUERY_LENGTH = 3
export const MAX_NAME_MATCHES = 5

export function normalizeNameQuery(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}+/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
}

function levenshtein(a: string, b: string): number {
  if (a === b) return 0
  if (!a.length) return b.length
  if (!b.length) return a.length
  const prev = new Array<number>(b.length + 1)
  const next = new Array<number>(b.length + 1)
  for (let j = 0; j <= b.length; j++) prev[j] = j
  for (let i = 1; i <= a.length; i++) {
    next[0] = i
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      next[j] = Math.min(next[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
    }
    for (let j = 0; j <= b.length; j++) prev[j] = next[j]
  }
  return prev[b.length]
}

/** Higher is better. `null` means the name should not appear in results. */
export function scoreParkName(name: string, query: string): number | null {
  const q = normalizeNameQuery(query)
  if (q.length < MIN_NAME_QUERY_LENGTH) return null
  const n = normalizeNameQuery(name)
  if (!n) return null

  if (n === q) return 1000
  if (n.startsWith(q)) return 900 - Math.min(n.length - q.length, 80)

  const words = n.split(" ").filter(Boolean)
  let bestWordPrefix: number | null = null
  for (let i = 0; i < words.length; i++) {
    const word = words[i]
    if (word.startsWith(q)) {
      const score = 800 - i * 12 - Math.min(word.length - q.length, 40)
      bestWordPrefix = bestWordPrefix == null ? score : Math.max(bestWordPrefix, score)
    }
  }
  if (bestWordPrefix != null) return bestWordPrefix

  const idx = n.indexOf(q)
  if (idx >= 0) return 700 - Math.min(idx, 80)

  let bestFuzzy: number | null = null
  const maxDistance = q.length >= 6 ? 2 : 1
  for (let i = 0; i < words.length; i++) {
    const word = words[i]
    const target = word.slice(0, q.length)
    if (!target) continue
    const distance = levenshtein(q, target)
    if (distance === 0 || distance > maxDistance) continue
    const score = 400 - distance * 60 - i * 8
    bestFuzzy = bestFuzzy == null ? score : Math.max(bestFuzzy, score)
  }
  return bestFuzzy
}

export function rankParkNameMatches<T extends { name: string }>(
  parks: readonly T[],
  query: string,
  limit = MAX_NAME_MATCHES,
): T[] {
  const q = normalizeNameQuery(query)
  if (q.length < MIN_NAME_QUERY_LENGTH) return []

  const scored: { park: T; score: number }[] = []
  for (const park of parks) {
    const score = scoreParkName(park.name, q)
    if (score == null) continue
    scored.push({ park, score })
  }
  scored.sort((a, b) => b.score - a.score || a.park.name.localeCompare(b.park.name))
  return scored.slice(0, limit).map((item) => item.park)
}

export function nameMatchRange(name: string, query: string): { start: number; end: number } | null {
  const q = query.trim()
  if (q.length < MIN_NAME_QUERY_LENGTH) return null
  const idx = name.toLowerCase().indexOf(q.toLowerCase())
  if (idx >= 0) return { start: idx, end: idx + q.length }

  const words = name.split(/(\s+)/)
  let cursor = 0
  const needle = normalizeNameQuery(q)
  for (const part of words) {
    const normalized = normalizeNameQuery(part)
    if (normalized.startsWith(needle) || normalized.includes(needle)) {
      const local = part.toLowerCase().indexOf(q.toLowerCase())
      if (local >= 0) return { start: cursor + local, end: cursor + local + q.length }
      return { start: cursor, end: cursor + part.length }
    }
    cursor += part.length
  }
  return null
}
