import { addDays } from './format.js'

// Status on one radar date. Each has a colour, a symbol and a text: never colour alone.
export const STATUS = {
  c: { key: 'connected', color: '#268B65', symbol: '✓' },
  i: { key: 'isolated', color: '#D94C4C', symbol: '✕' },
  u: { key: 'uncertain', color: '#B7791F', symbol: '?' },
  b: { key: 'boat_dependent', color: '#6B7785', symbol: '~' },
}

/** One-letter status of a village on radar date `index` ('u' when unknown). */
export function statusCode(flood, villageId, index) {
  return flood.status.villages[villageId]?.[index] ?? 'u'
}

export function villageName(v, lang) {
  return (lang === 'bn' && v.name_local) || v.name
}

/**
 * When household supplies may run out: the earliest day isolation could have started plus the supply days.
 * The earliest day (not the first day isolation was seen) keeps relief planning on the early side.
 */
export function supplyEstimate(v, supplyDays) {
  return v.isolated_from_earliest ? addDays(v.isolated_from_earliest, supplyDays) : null
}

/** Isolated villages, most urgent first (as the pipeline ranks them). */
export function rankedIsolated(villages) {
  return villages
    .filter((v) => v.outcome === 'isolated')
    .sort((a, b) => (a.urgency_rank ?? 999) - (b.urgency_rank ?? 999))
}

/** Straight-line distance in km (not a road distance). */
export function distanceKm(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180
  const x = (lon2 - lon1) * r * Math.cos(((lat1 + lat2) / 2) * r)
  const y = (lat2 - lat1) * r
  return Math.sqrt(x * x + y * y) * 6371
}

const ARROWS = ['↑', '↗', '→', '↘', '↓', '↙', '←', '↖']

/** An arrow from point 1 to point 2, readable in any language. */
export function compassArrow(lat1, lon1, lat2, lon2) {
  const x = (lon2 - lon1) * Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180)
  const bearing = ((Math.atan2(x, lat2 - lat1) * 180) / Math.PI + 360) % 360
  return ARROWS[Math.floor((bearing + 22.5) / 45) % 8]
}

export function nearest(items, lat, lon) {
  let best = null
  for (const it of items) {
    const km = distanceKm(lat, lon, it.lat, it.lon)
    if (!best || km < best.km) best = { item: it, km }
  }
  return best
}
