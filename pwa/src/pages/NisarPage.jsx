import 'leaflet/dist/leaflet.css'
import { ChartLine, Info, Layers, Radio, Satellite, Sprout, Waves } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, GeoJSON, ImageOverlay, MapContainer, Tooltip, useMap } from 'react-leaflet'
import PageHead from '../components/PageHead.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { formatDate, formatNumber } from '../lib/format.js'
import { DATA_BASE } from '../services/data.js'

// NISAR L-band layers made by scripts/nisar_polarization.py and exported by scripts/build_pwa.py (data/nisar/).
// Every number on this page is read from that export; nothing is computed or filled in here.

const LAYERS = ['s1_water', 'hh_water', 'hv_water', 'hh', 'hv', 'rgb']
const AREA = { color: '#ffd23f', weight: 2, dashArray: '6 6', fill: false }

function useNisar() {
  const [data, setData] = useState({ state: 'loading' })
  useEffect(() => {
    let alive = true
    fetch(`${DATA_BASE}/nisar/index.json`)
      .then((r) => (r.ok && (r.headers.get('content-type') || '').includes('json') ? r.json() : null))
      .then(async (index) => {
        if (!index?.regions?.length) return alive && setData({ state: 'none' })
        const extras = await Promise.all(index.regions.map(async (reg) => {
          const get = (f) => fetch(`${DATA_BASE}/nisar/${reg.id}/${f}`).then((r) => (r.ok ? r.json() : null)).catch(() => null)
          return {
            area: reg.has_area ? await get('area.geojson') : null,
            villages: reg.has_villages ? await get('villages.geojson') : null,
            gap: reg.has_village_water ? await get('village_water.json') : null,
          }
        }))
        if (alive) setData({ state: 'ready', regions: index.regions.map((reg, i) => ({ ...reg, ...extras[i] })) })
      })
      .catch(() => alive && setData({ state: 'none' }))
    return () => {
      alive = false
    }
  }, [])
  return data
}

/** Clips the right-hand overlay so only the part right of the swipe line shows. */
function Swipe({ overlay, pct, layer }) {
  const map = useMap()
  useEffect(() => {
    function update() {
      const el = overlay.current?.getElement?.()
      if (!el) return
      const box = map.getContainer().getBoundingClientRect()
      const img = el.getBoundingClientRect()
      const line = box.left + (box.width * pct) / 100
      el.style.clipPath = `inset(0 0 0 ${Math.max(0, line - img.left)}px)`
    }
    update()
    const timers = [50, 300, 1000].map((ms) => setTimeout(update, ms))   // after the new image has its size
    map.on('move zoom zoomend viewreset resize load', update)
    return () => {
      timers.forEach(clearTimeout)
      map.off('move zoom zoomend viewreset resize load', update)
    }
  }, [map, overlay, pct, layer])        // a new right-hand layer is a new image: clip it too
  return null
}

function Compare({ region, scene }) {
  const t = useT()
  const { lang } = useLanguage()
  const available = LAYERS.filter((k) => scene.layers[k])
  // NISAR water on the right (HH when this date has an HH map, otherwise HV); on the left something different to
  // compare with: Sentinel-1's water when there is one within 3 days, otherwise the radar picture itself
  const rightStart = ['hh_water', 'hv_water', 'hh'].find((k) => available.includes(k)) || available[0]
  const [left, setLeft] = useState(['s1_water', 'rgb', 'hh', 'hv'].find((k) => available.includes(k) && k !== rightStart)
    || available.find((k) => k !== rightStart) || available[0])
  const [right, setRight] = useState(rightStart)
  const [pct, setPct] = useState(50)
  const rightRef = useRef(null)
  const L = available.includes(left) ? left : available[0]
  const R = available.includes(right) ? right : available[available.length - 1]
  const url = (k) => `${DATA_BASE}/nisar/${region.id}/${scene.layers[k]}`
  const villageName = (p) => (lang === 'bn' && p.name_bn) || p.name

  return (
    <div className="card">
      <div className="nisar-pick">
        <label className="field">
          <span className="field-label">{t('nisar_left')}</span>
          <select value={L} onChange={(e) => setLeft(e.target.value)}>
            {available.map((k) => <option key={k} value={k}>{t(`layer_${k}`)}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{t('nisar_right')}</span>
          <select value={R} onChange={(e) => setRight(e.target.value)}>
            {available.map((k) => <option key={k} value={k}>{t(`layer_${k}`)}</option>)}
          </select>
        </label>
      </div>
      <div className="mapwrap swipe-wrap">
        <MapContainer key={`${region.id}-${scene.date}`} className="map nisar-map" bounds={region.bounds}
          boundsOptions={{ padding: [4, 4] }} zoomSnap={0.25} zoomAnimation={false} attributionControl>
          <ImageOverlay key={`l-${L}`} url={url(L)} bounds={region.bounds} opacity={1} zIndex={1}
            attribution="NISAR: NASA-ISRO (ASF DAAC); Sentinel-1: ESA Copernicus" />
          <ImageOverlay key={`r-${R}`} ref={rightRef} url={url(R)} bounds={region.bounds} opacity={1} zIndex={2} />
          <Swipe overlay={rightRef} pct={pct} layer={R} />
          {region.area && <GeoJSON data={region.area} style={AREA} interactive={false} />}
          {region.villages?.features.map((f, i) => (
            <CircleMarker key={i} center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]} radius={4}
              pathOptions={{ color: '#fff', weight: 1.5, fillColor: '#102D46', fillOpacity: 1 }}>
              <Tooltip>{villageName(f.properties)}</Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
        <span className="swipe-line" style={{ left: `${pct}%` }} aria-hidden="true" />
        <span className="swipe-tag left">{t(`layer_${L}`)}</span>
        <span className="swipe-tag right">{t(`layer_${R}`)}</span>
      </div>
      <label className="field-label" htmlFor="swipe">{t('nisar_swipe')}</label>
      <input id="swipe" type="range" min={0} max={100} value={pct} onChange={(e) => setPct(Number(e.target.value))} />
      {(L === 'rgb' || R === 'rgb') && <p className="muted small">{t('nisar_rgb_legend')}</p>}
    </div>
  )
}

const SERIES = [
  { key: 'hh', name: 'NISAR HH', dash: '', shape: 'circle' },
  { key: 'hv', name: 'NISAR HV', dash: '6 4', shape: 'square' },
  { key: 's1', name: 'Sentinel-1', dash: '2 3', shape: 'triangle' },
]

function seriesValue(scene, key) {
  if (key === 's1') return scene.sentinel1?.water_km2 ?? null
  return scene[key]?.status === 'otsu' ? scene[key].water_km2 : null
}

/** Water area on each NISAR date. Lines differ by dash and marker shape, and every number is also written as text. */
function Series({ scenes }) {
  const t = useT()
  const { lang } = useLanguage()
  const W = 320
  const H = 150
  const pad = { l: 34, r: 10, t: 10, b: 24 }
  const top = Math.max(...scenes.flatMap((s) => SERIES.map((x) => seriesValue(s, x.key) ?? 0)), 1)
  // placed by the real date, not evenly: the gaps between NISAR passes range from 2 to 24 days
  const ms = scenes.map((s) => new Date(`${s.date}T00:00:00Z`).getTime())
  const span = ms[ms.length - 1] - ms[0]
  const x = (i) => pad.l + 6 + (scenes.length === 1 || !span ? (W - pad.l - pad.r) / 2 : ((ms[i] - ms[0]) * (W - pad.l - pad.r - 6)) / span)
  const y = (v) => pad.t + (1 - v / top) * (H - pad.t - pad.b)
  const mark = (shape, cx, cy) => (shape === 'circle' ? <circle cx={cx} cy={cy} r="4" /> : shape === 'square'
    ? <rect x={cx - 4} y={cy - 4} width="8" height="8" /> : <polygon points={`${cx},${cy - 5} ${cx + 5},${cy + 4} ${cx - 5},${cy + 4}`} />)
  return (
    <div className="card">
      <h2><ChartLine size={20} aria-hidden="true" /> {t('nisar_series_title')}</h2>
      <svg className="ts-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('nisar_series_alt')}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={pad.l} x2={W - pad.r} y1={y(top * f)} y2={y(top * f)} className="ts-grid" />
            <text x={pad.l - 4} y={y(top * f) + 3} textAnchor="end" className="ts-axis">{formatNumber(Math.round(top * f), lang)}</text>
          </g>
        ))}
        {scenes.map((s, i) => (i === 0 || i === scenes.length - 1 || (scenes.length <= 5) || i === Math.floor(scenes.length / 2)) && <text key={s.date} x={x(i)} y={H - 6} textAnchor={i === scenes.length - 1 && scenes.length > 1 ? 'end' : i === 0 ? 'start' : 'middle'} className="ts-axis">{formatDate(s.date, lang, true)}</text>)}
        {SERIES.map((ser, k) => {
          const pts = scenes.map((s, i) => [x(i), seriesValue(s, ser.key)]).filter(([, v]) => v != null)
          return (
            <g key={ser.key} className={`ts-line ts-${k}`}>
              {pts.length > 1 && <polyline points={pts.map(([px, v]) => `${px},${y(v)}`).join(' ')} strokeDasharray={ser.dash} fill="none" />}
              {pts.map(([px, v]) => <g key={px}>{mark(ser.shape, px, y(v))}</g>)}
            </g>
          )
        })}
      </svg>
      <ul className="ts-legend small">
        {SERIES.map((ser, k) => <li key={ser.key} className={`ts-${k}`}><svg width="34" height="12" aria-hidden="true"><line x1="0" x2="26" y1="6" y2="6" strokeDasharray={ser.dash} />{mark(ser.shape, 17, 6)}</svg> {ser.name}</li>)}
      </ul>
      <ul className="plain small">
        {scenes.map((s) => (
          <li key={s.date}>{t('nisar_series_row', {
            d: formatDate(s.date, lang),
            hh: seriesValue(s, 'hh') == null ? '—' : formatNumber(seriesValue(s, 'hh'), lang, 0),
            hv: seriesValue(s, 'hv') == null ? '—' : formatNumber(seriesValue(s, 'hv'), lang, 0),
            s1: seriesValue(s, 's1') == null ? '—' : formatNumber(seriesValue(s, 's1'), lang, 0),
          })}</li>
        ))}
      </ul>
      <p className="muted small">{t('nisar_series_note')}</p>
    </div>
  )
}

/** Villages ranked by how much more water NISAR sees nearby than Sentinel-1 (likely water under plants). */
function Gap({ region, scene }) {
  const t = useT()
  const { lang } = useLanguage()
  const day = region.gap?.dates.find((d) => d.date === scene.date)
  const pct = (v) => formatNumber(Math.round(v * 100), lang)
  const rows = day ? Object.values(day.villages).filter((v) => v.hidden != null).sort((a, b) => b.hidden - a.hidden).slice(0, 8) : []
  return (
    <div className="card">
      <h2><Waves size={20} aria-hidden="true" /> {t('nisar_gap_title')}</h2>
      {!day || !rows.length ? <p className="muted">{t('nisar_gap_none')}</p> : (
        <>
          <p>{t('nisar_gap_head', { n: formatNumber(day.villages_with_a_gap, lang), total: formatNumber(Object.keys(day.villages).length, lang), m: pct(day.median_hidden) })}</p>
          <ul className="plain">
            {rows.map((v) => (
              <li key={v.name + v.nisar} className="gap-row">
                <span>{t('nisar_gap_row', { name: (lang === 'bn' && v.name_bn) || v.name, a: pct(v.nisar), b: pct(v.sentinel1), g: pct(v.hidden) })}</span>
                <span className="gap-bar" aria-hidden="true"><span style={{ width: `${Math.min(100, Math.round(v.hidden * 100))}%` }} /></span>
              </li>
            ))}
          </ul>
          <p className="muted small">{t('nisar_gap_note')}</p>
        </>
      )}
    </div>
  )
}

function Numbers({ scene }) {
  const t = useT()
  const { lang } = useLanguage()
  const n = (v, d = 0) => formatNumber(v, lang, d)
  const s1 = scene.sentinel1
  const g = scene.groups
  return (
    <div className="card">
      <h2><Layers size={20} aria-hidden="true" /> {t('nisar_numbers')}</h2>
      <ul className="plain">
        {['hh', 'hv'].map((pol) => (
          <li key={pol}>{scene[pol].status === 'otsu'
            ? t('nisar_water_line', { name: `NISAR ${pol.toUpperCase()}`, km: n(scene[pol].water_km2, 1) })
            : t('nisar_unclassified', { pol: `NISAR ${pol.toUpperCase()}` })}</li>
        ))}
        {s1 ? (
          <>
            <li>{t('nisar_s1_line', { d: formatDate(s1.date, lang), g: n(s1.gap_days), km: n(s1.water_km2, 1) })}</li>
            {['hh', 'hv'].filter((pol) => s1[`${pol}_vs_s1`]?.share_of_b_in_a != null).map((pol) => (
              <li key={pol}><strong>{t('nisar_confirm', { pol: pol.toUpperCase(), p: n(s1[`${pol}_vs_s1`].share_of_b_in_a * 100, 1) })}</strong></li>
            ))}
          </>
        ) : <li>{t('nisar_no_s1')}</li>}
        {scene.hh_vs_hv?.iou != null && <li>{t('nisar_hhhv', { v: n(scene.hh_vs_hv.iou, 2) })}</li>}
      </ul>
      {g && (
        <>
          <h3 className="sub-title">{t('nisar_groups_title')}</h3>
          <ul className="plain small">
            {[['water_in_both', 'nisar_group_both'], ['water_in_nisar_hh_only', 'nisar_group_only'], ['dry_in_both', 'nisar_group_dry']]
              .filter(([k]) => g[k]).map(([k, label]) => (
                <li key={k}><strong>{t(label)}:</strong> {t('nisar_group_row', { hh: n(g[k].hh_db, 1), hv: n(g[k].hv_db, 1), d: n(g[k].hh_minus_hv_db, 1) })}</li>
              ))}
          </ul>
          <p className="muted small">{t('nisar_groups_note')}</p>
        </>
      )}
    </div>
  )
}

export default function NisarPage() {
  const t = useT()
  const { lang } = useLanguage()
  const data = useNisar()
  const [regionId, setRegionId] = useState(null)
  const [sceneIdx, setSceneIdx] = useState(null)
  // Sunamganj first (the home study area), unless another area was chosen
  const region = useMemo(() => data.regions?.find((r) => r.id === regionId)
    || data.regions?.find((r) => r.id.startsWith('sunamganj')) || data.regions?.[0], [data, regionId])
  const scenes = region?.scenes || []
  // opens on the latest date that has a Sentinel-1 map to compare with; the whole season is in the chart below
  const lastCompared = scenes.reduce((k, s, i) => (s.sentinel1 ? i : k), scenes.length - 1)
  const scene = scenes[sceneIdx ?? lastCompared]

  return (
    <section>
      <PageHead Icon={Satellite} title={t('nisar_title')} sub={t('nisar_sub')} />
      <div className="card">
        <p>{t('nisar_intro')}</p>
      </div>
      {data.state === 'loading' && <p className="muted">{t('loading')}</p>}
      {data.state === 'none' && <p className="muted">{t('nisar_none')}</p>}
      {region && scene && (
        <>
          <div className="card">
            <span className="field-label">{t('nisar_area')}</span>
            <div className="chips" role="group" aria-label={t('nisar_area')}>
              {data.regions.map((r) => (
                <button key={r.id} className={r.id === region.id ? 'chip on' : 'chip'} aria-pressed={r.id === region.id}
                  onClick={() => { setRegionId(r.id); setSceneIdx(null) }}>{r.name.split(':')[0]}</button>
              ))}
            </div>
            <span className="field-label">{t('nisar_date')}</span>
            <div className="chips" role="group" aria-label={t('nisar_date')}>
              {scenes.map((s, i) => (
                <button key={s.date} className={s === scene ? 'chip on' : 'chip'} aria-pressed={s === scene}
                  onClick={() => setSceneIdx(i)}>{formatDate(s.date, lang, true)}</button>
              ))}
            </div>
          </div>
          <Compare key={`${region.id}-${scene.date}`} region={region} scene={scene} />
          <Numbers scene={scene} />
          {scenes.length > 1 && <Series scenes={scenes} />}
          {region.gap && <Gap region={region} scene={scene} />}
        </>
      )}
      <div className="card">
        <h2><Sprout size={20} aria-hidden="true" /> {t('nisar_why_title')}</h2>
        <p>{t('nisar_why')}</p>
      </div>
      <div className="card">
        <h2><Radio size={20} aria-hidden="true" /> {t('nisar_pol_title')}</h2>
        <p>{t('nisar_pol')}</p>
      </div>
      <div className="card">
        <h2><Layers size={20} aria-hidden="true" /> {t('nisar_hv_title')}</h2>
        <p>{t('nisar_hv_text')}</p>
      </div>
      <p className="notice"><Info size={18} aria-hidden="true" /><span>{t('nisar_limits')}</span></p>
    </section>
  )
}
