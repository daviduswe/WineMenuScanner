import { useMemo, useState } from 'react'
import { analyzeMenu } from './api/client'
import type { Wine } from './types/wine'
import UploadCard from './components/UploadCard'
import WineTable from './components/WineTable'
import WineDetail from './components/WineDetail'

export default function App() {
  const [rawText, setRawText] = useState<string>('')
  const [wines, setWines] = useState<Wine[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)

  // List state
  const [query, setQuery] = useState('')
  const [section, setSection] = useState<string>('')
  const [sortKey, setSortKey] = useState<'name' | 'vintage' | 'price'>('name')

  const selectedWine = useMemo(
    () => wines.find((w) => w.id === selectedId) ?? null,
    [wines, selectedId],
  )

  const sections = useMemo(() => {
    const s = new Set<string>()
    wines.forEach((w) => {
      const g = w.wineGroup ?? w.section
      if (g) s.add(g)
    })
    return Array.from(s).sort()
  }, [wines])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    let out = wines

    if (q) {
      out = out.filter((w) => {
        const hay = `${w.name ?? ''} ${w.producer ?? ''} ${w.region ?? ''}`.toLowerCase()
        return hay.includes(q)
      })
    }

    if (section) {
      out = out.filter((w) => (w.wineGroup ?? w.section ?? '') === section)
    }

    out = [...out].sort((a, b) => {
      if (sortKey === 'name') return (a.name ?? '').localeCompare(b.name ?? '')
      if (sortKey === 'vintage') return (b.vintage ?? 0) - (a.vintage ?? 0)

      // sort by bottle price primarily; fall back to glass; N/A last
      const aPrice = a.price?.bottle ?? a.price?.glass
      const bPrice = b.price?.bottle ?? b.price?.glass
      if (aPrice == null && bPrice == null) return 0
      if (aPrice == null) return 1
      if (bPrice == null) return -1
      return aPrice - bPrice
    })

    return out
  }, [wines, query, section, sortKey])

  async function onUpload(file: File) {
    setLoading(true)
    setError(null)
    setSelectedId(null)

    try {
      const res = await analyzeMenu(file)
      setRawText(res.rawText)
      setWines(res.wines)

      // If OCR ran but no wines parsed, surface a helpful message.
      if ((res.wines?.length ?? 0) === 0) {
        if (!res.rawText || res.rawText.trim().length === 0) {
          setError('OCR returned no text. Try a higher-resolution, well-lit photo, then re-upload.')
        } else {
          setError('OCR succeeded but no wine rows were detected. See “OCR raw text” below for troubleshooting.')
        }
      }
    } catch (e: any) {
      setError(e?.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  function onReset() {
    setRawText('')
    setWines([])
    setSelectedId(null)
    setQuery('')
    setSection('')
    setSortKey('name')
    setError(null)
  }

  if (selectedWine) {
    return (
      <div className="page">
        <header className="topbar">
          <div className="brand">Wine Menu Scanner</div>
          <button className="btn" onClick={() => setSelectedId(null)}>
            Back to list
          </button>
        </header>

        <main className="container">
          <WineDetail wine={selectedWine} />
        </main>
      </div>
    )
  }

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">Wine Menu Scanner</div>
        <div className="topbar-actions">
          {wines.length > 0 ? (
            <button className="btn" onClick={onReset}>
              New upload
            </button>
          ) : null}
        </div>
      </header>

      <main className="container">
        <UploadCard onUpload={onUpload} loading={loading} />

        {error ? <div className="alert alert-error">{error}</div> : null}

        {wines.length === 0 && !loading && !error && !rawText ? (
          <div className="hint">Upload a wine menu image to see results.</div>
        ) : null}

        {wines.length > 0 ? (
          <WineTable
            wines={filtered}
            sections={sections}
            query={query}
            section={section}
            sortKey={sortKey}
            onQueryChange={setQuery}
            onSectionChange={setSection}
            onSortKeyChange={setSortKey}
            onSelect={(id) => setSelectedId(id)}
          />
        ) : null}

        {/* Always show raw text if present (even when no wines parsed) */}
        {rawText ? (
          <details className="raw" open={wines.length === 0}>
            <summary>OCR raw text</summary>
            <pre>{rawText}</pre>
          </details>
        ) : null}
      </main>
    </div>
  )
}
