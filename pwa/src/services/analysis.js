import { useEffect, useState } from 'react'
import { DATA_BASE } from './data.js'

// The planning analyses of one flood (scripts/road_criticality.py, scripts/relief_prepositioning.py), exported by
// build_pwa.py. Each file is optional: a flood without an analysis simply has none, and nothing is shown for it.

async function optional(path) {
  try {
    const r = await fetch(`${DATA_BASE}/${path}`)
    if (!r.ok || !(r.headers.get('content-type') || '').includes('json')) return null    // the app page, not data
    return await r.json()
  } catch {
    return null
  }
}

/** {critical, roads, relief, buildings} for the flood (each null when it does not exist); null while loading. */
export function useAnalysis(floodId) {
  const [loaded, setLoaded] = useState({ id: null })
  useEffect(() => {
    if (!floodId) return undefined
    let alive = true
    Promise.all([optional(`${floodId}/critical.json`), optional(`${floodId}/critical_roads.geojson`),
      optional(`${floodId}/relief.json`), optional(`${floodId}/buildings.json`)])
      .then(([critical, roads, relief, buildings]) => alive && setLoaded({ id: floodId, critical, roads, relief, buildings }))
    return () => {
      alive = false
    }
  }, [floodId])
  return loaded.id === floodId ? loaded : null
}

/** Road stretches that were a village's only remaining road link on radar date `index`, most people first. */
export function stretchesOn(roads, index) {
  return (roads?.features || [])
    .filter((f) => f.properties.kind === 'date' && f.properties.d.includes(index))
    .sort((a, b) => b.properties.population - a.properties.population)
}

/** The same test with every mapped road open (before any flood). */
export function dryStretches(roads) {
  return (roads?.features || []).filter((f) => f.properties.kind === 'dry').sort((a, b) => a.properties.rank - b.properties.rank)
}

export function isFragile(critical, villageId, index) {
  return critical?.fragile?.[villageId]?.[index] === '1'
}
