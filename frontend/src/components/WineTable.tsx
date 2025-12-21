import type { Wine } from '../types/wine'

type Props = {
  wines: Wine[]
  sections: string[]
  query: string
  section: string
  sortKey: 'name' | 'price' | 'glassPrice' | 'group'
  onQueryChange: (v: string) => void
  onSectionChange: (v: string) => void
  onSortKeyChange: (v: 'name' | 'price' | 'glassPrice' | 'group') => void
  onSelect: (id: string) => void
}

function fmtPrice(value?: number | null, currency?: string | null) {
  if (value == null) return 'N/A'
  const cur = currency ?? ''
  return `${cur}${value}`
}

function isNoiseRow(w: Wine) {
  const name = (w.name ?? '').trim()
  // Common OCR noise glyphs: dot/bullets, underscores, hyphens, and related unicode dashes.
  const onlyNoiseGlyphs = name.length > 0 && /^[\s._\-\u00b7\u2219\u2022\u2043\u2212\u2010\u2011\u2012\u2013\u2014\u2015\u208b\u2099\u20bf\u208b\u208d\u208e\u208a\u208c\u208f\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089]+$/.test(name)
  const glass = w.price?.glass
  const bottle = w.price?.bottle
  const noPrices = glass == null && bottle == null
  return onlyNoiseGlyphs && noPrices
}

export default function WineTable({
  wines,
  sections,
  query,
  section,
  sortKey,
  onQueryChange,
  onSectionChange,
  onSortKeyChange,
  onSelect,
}: Props) {
  const visibleWines = wines.filter((w) => !isNoiseRow(w))

  return (
    <section className="card">
      <div className="card-row">
        <div>
          <div className="card-title">Wine List</div>
          <div className="card-subtitle">Click a row to view full details.</div>
        </div>
        <div className="filters">
          <input
            className="input"
            placeholder="Search (name / producer / region)"
            value={query}
            onChange={(e) => onQueryChange(e.currentTarget.value)}
          />
          <select className="select" value={section} onChange={(e) => onSectionChange(e.currentTarget.value)}>
            <option value="">All groups</option>
            {sections.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select className="select" value={sortKey} onChange={(e) => onSortKeyChange(e.currentTarget.value as any)}>
            <option value="name">Sort: Name</option>
            <option value="price">Sort: Bottle Price</option>
            <option value="glassPrice">Sort: Glass Price</option>
            <option value="group">Sort: Group</option>
          </select>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Wine</th>
              <th className="right">Glass</th>
              <th className="right">Bottle</th>
            </tr>
          </thead>
          <tbody>
            {visibleWines.map((w) => (
              <tr key={w.id} className="row" onClick={() => onSelect(w.id)}>
                <td>{w.wineGroup ?? '—'}</td>
                <td>
                  <div>{w.name ?? '—'}</div>
                  {w.description ? <div className="muted small">{w.description}</div> : null}
                </td>
                <td className="right">{fmtPrice(w.price?.glass, w.price?.currency)}</td>
                <td className="right">{fmtPrice(w.price?.bottle, w.price?.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {visibleWines.length === 0 ? <div className="hint">No wines found for your filters.</div> : null}
    </section>
  )
}
