import type { Wine } from '../types/wine'

type Props = {
  wine: Wine
}

function fmtPrice(value?: number | null, currency?: string | null) {
  if (value == null) return 'N/A'
  const cur = currency ?? ''
  return `${cur}${value}`
}

export default function WineDetail({ wine }: Props) {
  const group = wine.wineGroup ?? wine.section

  return (
    <section className="card">
      <div className="detail-title">{wine.name ?? 'Unknown Wine'}</div>
      <div className="detail-sub">{group ?? 'Ungrouped'}</div>

      {wine.description ? <div className="hint" style={{ marginTop: 8 }}>{wine.description}</div> : null}

      <div className="grid">
        <div className="kv">
          <div className="k">Wine group</div>
          <div className="v">{group ?? '—'}</div>
        </div>
        <div className="kv">
          <div className="k">Vintage</div>
          <div className="v">{wine.vintage ?? '—'}</div>
        </div>
        <div className="kv">
          <div className="k">Glass Price</div>
          <div className="v">{fmtPrice(wine.price?.glass, wine.price?.currency)}</div>
        </div>
        <div className="kv">
          <div className="k">Bottle Price</div>
          <div className="v">{fmtPrice(wine.price?.bottle, wine.price?.currency)}</div>
        </div>
        <div className="kv">
          <div className="k">Producer</div>
          <div className="v">{wine.producer ?? '—'}</div>
        </div>
        <div className="kv">
          <div className="k">Region</div>
          <div className="v">{wine.region ?? '—'}</div>
        </div>
        <div className="kv">
          <div className="k">Grape</div>
          <div className="v">{wine.grape ?? '—'}</div>
        </div>
      </div>

      <div className="rawline">
        <div className="k">Source line</div>
        <div className="v mono">{wine.rawText}</div>
      </div>
    </section>
  )
}
