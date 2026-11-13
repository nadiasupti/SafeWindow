import L from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import { useMap } from 'react-leaflet'
import { useLanguage, useT } from '../i18n/language.js'
import { formatNumber } from '../lib/format.js'

// Mapped buildings (scripts/building_exposure.py) summed per cell (500 m, buildings.json cell_m), coloured by the chosen radar date.
// Thousands of cells: drawn on one canvas, not as React components, so the map stays smooth on a phone.
// cell = [lat, lon, buildings, far from roads, isolated per date, uncertain per date, near water per date]

const COLOUR = { i: '#D94C4C', u: '#B7791F', c: '#268B65', b: '#6B7785' }

// a per-date list is null (all zero) or base-36 numbers joined by "." (scripts/build_pwa.py, buildings_file)
const at = (packed, index) => (packed ? parseInt(packed.split('.')[index], 36) || 0 : 0)

function cellState(cell, index) {
  const [, , n, far, iso, unc, wet] = cell
  const i = at(iso, index)
  const u = at(unc, index)
  const w = at(wet, index)
  const kind = i > 0 ? 'i' : u > 0 ? 'u' : far >= n ? 'b' : 'c'
  return { n, far, i, u, w, kind }
}

export default function BuildingsLayer({ data, index }) {
  const map = useMap()
  const t = useT()
  const { lang } = useLanguage()
  const renderer = useMemo(() => L.canvas({ padding: 0.3 }), [])
  // the text function changes on every render; the layer is redrawn only when the data, date or language change
  const tRef = useRef(t)
  useEffect(() => {
    tRef.current = t
  })

  useEffect(() => {
    const group = L.layerGroup()
    const f = (v) => formatNumber(v, lang)
    for (const cell of data.cells) {
      const s = cellState(cell, index)
      L.circleMarker([cell[0], cell[1]], {
        renderer, radius: Math.min(10, 2 + Math.sqrt(s.n) / 2),
        color: s.w > 0 ? '#1E6EE6' : '#ffffff', weight: s.w > 0 ? 2 : 0.6,
        fillColor: COLOUR[s.kind], fillOpacity: s.kind === 'i' ? 0.85 : 0.6,
      }).bindTooltip(tRef.current('bld_tip', { n: f(s.n), i: f(s.i), u: f(s.u), w: f(s.w), f: f(s.far) })).addTo(group)
    }
    group.addTo(map)
    return () => {
      group.remove()
    }
  }, [map, data, index, renderer, lang])
  return null
}
