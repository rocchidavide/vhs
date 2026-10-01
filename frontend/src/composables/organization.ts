/** Pure helpers for personal tags and collections, kept out of components for testing. */

import type { TagRef } from '@/api/organization'
import { currentLocale } from '@/i18n'

/** Return a copy of items with the element at `from` moved to `to`. */
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  const result = [...items]
  if (from < 0 || from >= result.length || to < 0 || to >= result.length || from === to) {
    return result
  }
  const [moved] = result.splice(from, 1)
  result.splice(to, 0, moved as T)
  return result
}

export interface TagSuggestions<T extends TagRef> {
  matches: T[]
  /** Name to offer as "Create personal tag", or null if it already exists or is empty. */
  create: string | null
}

/** Tags matching the query (excluding those already assigned) and whether to offer creation. */
export function suggestTags<T extends TagRef>(
  tags: readonly T[],
  query: string,
  assignedIds: readonly number[] = [],
  limit = 8,
  locale: string = currentLocale(),
): TagSuggestions<T> {
  const name = query.trim().replace(/\s+/g, ' ')
  const needle = name.toLocaleLowerCase(locale)
  const available = tags.filter((tag) => !assignedIds.includes(tag.id))
  const matches = available
    .filter((tag) => tag.name.toLocaleLowerCase(locale).includes(needle))
    .sort((a, b) => {
      const aStarts = a.name.toLocaleLowerCase(locale).startsWith(needle) ? 0 : 1
      const bStarts = b.name.toLocaleLowerCase(locale).startsWith(needle) ? 0 : 1
      return aStarts - bStarts || a.name.localeCompare(b.name, locale)
    })
    .slice(0, limit)
  const exists = tags.some((tag) => tag.name.toLocaleLowerCase(locale) === needle)
  return { matches, create: name && !exists ? name : null }
}
