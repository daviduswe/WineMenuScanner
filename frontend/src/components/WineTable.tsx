import type { Wine } from '../types/wine'

type Props = {
  wines: Wine[]
  sections: string[]
  query: string
  section: string
  sortKey: 'name' | 'vintage' | 'price'
  onQueryChange: (v: string) => void
  onSectionChange: (v: string) => void
  onSortKeyChange: (v: 'name' | 'vintage' | 'price') => void
  onSelect: (id: string) => void
}

function fmtPrice(value?: number | null, currency?: string | null) {
  if (value == null) return 'N/A'
  const cur = currency ?? ''
  return `${cur}${value}`
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
            <option value="vintage">Sort: Vintage</option>
            <option value="price">Sort: Bottle Price</option>
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
            {wines.map((w) => (
              <tr key={w.id} className="row" onClick={() => onSelect(w.id)}>
                <td>{w.wineGroup ?? '—'}</td>
                <td>{w.name ?? '—'}</td>
                <td className="right">{fmtPrice(w.price?.glass, w.price?.currency)}</td>
                <td className="right">{fmtPrice(w.price?.bottle, w.price?.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {wines.length === 0 ? <div className="hint">No wines found for your filters.</div> : null}
    </section>
  )
}
