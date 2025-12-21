export type Price = {
  currency?: string | null
  bottle?: number | null
  glass?: number | null
}

export type Wine = {
  id: string
  rawText: string

  wineGroup?: string | null
  section?: string | null

  name?: string | null
  producer?: string | null
  region?: string | null
  vintage?: number | null
  grape?: string | null

  description?: string | null

  price?: Price
}

export type AnalyzeResponse = {
  rawText: string
  wines: Wine[]
}
