import { describe, expect, it } from 'vitest'

import { moveItem, suggestTags } from '../organization'

describe('moveItem', () => {
  it('moves an element forward and backward', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd'])
    expect(moveItem(['a', 'b', 'c', 'd'], 3, 1)).toEqual(['a', 'd', 'b', 'c'])
  })

  it('ignores out-of-range moves and never mutates the input', () => {
    const items = ['a', 'b']
    expect(moveItem(items, 0, 5)).toEqual(['a', 'b'])
    expect(moveItem(items, -1, 0)).toEqual(['a', 'b'])
    expect(items).toEqual(['a', 'b'])
  })
})

describe('suggestTags', () => {
  const tags = [
    { id: 1, name: 'Spot', slug: 'spot', color: '#fff' },
    { id: 2, name: 'Anni 90', slug: 'anni-90', color: '#fff' },
    { id: 3, name: 'Spot RAI', slug: 'spot-rai', color: '#fff' },
    { id: 4, name: 'Promo spot', slug: 'promo-spot', color: '#fff' },
  ]

  it('suggests matches, prefix first, excluding assigned tags', () => {
    const result = suggestTags(tags, 'spot', [1])

    expect(result.matches.map((tag) => tag.name)).toEqual(['Spot RAI', 'Promo spot'])
    expect(result.create).toBeNull()
  })

  it('offers creation for a new name, normalizing spaces', () => {
    expect(suggestTags(tags, '  Carosello   RAI ').create).toBe('Carosello RAI')
  })

  it('does not offer creation for an existing name in another case', () => {
    expect(suggestTags(tags, 'anni 90').create).toBeNull()
  })

  it('does not offer creation for an empty query', () => {
    expect(suggestTags(tags, '   ').create).toBeNull()
  })
})
