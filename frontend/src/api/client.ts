import type { AnalyzeResponse } from '../types/wine'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export async function analyzeMenu(file: File): Promise<AnalyzeResponse> {
  const form = new FormData()
  form.append('image', file)

  const res = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: 'POST',
    body: form,
  })

  if (!res.ok) {
    const msg = await res.text().catch(() => '')
    throw new Error(msg || `Analyze failed (${res.status})`)
  }

  return (await res.json()) as AnalyzeResponse
}
