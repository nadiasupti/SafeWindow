import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { ChartNoAxesCombined, ChevronDown, ChevronRight, LocateFixed, Map as MapIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Circle, GeoJSON, ImageOverlay, MapContainer, Marker, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { Link, useLocation } from 'react-router-dom'
import BuildingsLayer from '../components/BuildingsLayer.jsx'
import DateSlider from '../components/DateSlider.jsx'
import FloodBanner from '../components/FloodBanner.jsx'
import Loading from '../components/Loading.jsx'
import Notice from '../components/Notice.jsx'
import PageHead from '../components/PageHead.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { formatDate, formatNumber } from '../lib/format.js'
import { coverage } from '../lib/coverage.js'
import { getPosition } from '../lib/gps.js'
import { STATUS, statusCode, villageName } from '../lib/village.js'
import { stretchesOn, useAnalysis } from '../services/analysis.js'
import { floodImageUrl, loadLayer } from '../services/data.js'
import { useAppState } from '../state/appState.js'

// The offline base map is the flood's own road network, by class (1 major ... 4 tracks and paths).
const ROAD_STYLE = { 1: ['#c98a1b', 3.2], 2: ['#d9b45a', 2.4], 3: ['#a8a195', 1.3], 4: ['#bdb6a8', 1.0] }
const FLOODED_ROAD = { color: '#7A1020', weight: 2.5, opacity: 0.85 }
const ROUTE = { color: '#268B65', weight: 6, opacity: 0.95, dashArray: '10 8', lineCap: 'round' }
const AREA = { color: '#7d7a70', weight: 2, dashArray: '6 6', fill: false }
// The only remaining road link of some villages on the chosen date (scripts/road_criticality.py).
const CRITICAL = { color: '#6D28D9', weight: 7, opacity: 0.9, lineCap: 'round' }
// Online only, never cached: Esri's terms suit demos, not heavy public traffic.
const SATELLITE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

function villageIcon(code, selected) {
  const s = STATUS[code] || STATUS.u
  return L.divIcon({
    className: '',
    html: `<span class="vm${selected ? ' selected' : ''}" style="--c:${s.color}">${s.symbol}</span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

const SHELTER_ICON = L.divIcon({
  className: '',
  html: '<span class="sm" aria-hidden="true"><svg viewBox="0 0 24 24" width="11" height="11"><path d="M12 3 2 11h3v9h5v-6h4v6h5v-9h3z" fill="#102D46"/></svg></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
})

const RELIEF_ICON = L.divIcon({
  className: '',
  html: '<span class="rm" aria-hidden="true"><svg viewBox="0 0 24 24" width="12" height="12"><path d="M12 2 3 7v10l9 5 9-5V7zm0 2.3L18.7 8 12 11.7 5.3 8zM5 9.7l6 3.3v6.7l-6-3.3zm8 10V13l6-3.3v6.7z" fill="#fff"/></svg></span>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
})

const ME_ICON = L.divIcon({ className: '', html: '<span class="me"></span>', iconSize: [18, 18], iconAnchor: [9, 9] })

/** The flood's map layers; empty until they have loaded (never another flood's layers). */
function useLayers(floodId) {
  const [loaded, setLoaded] = useState({ id: null })
  useEffect(() => {
    let alive = true
    Promise.all(['area', 'roads', 'flooded_roads', 'routes', 'shelters'].map((n) => loadLayer(floodId, n)))
      .then(([area, roads, flooded, routes, shelters]) => alive && setLoaded({ id: floodId, area, roads, flooded, routes, shelters }))
    return () => {
      alive = false
    }
  }, [floodId])
  return loaded.id === floodId ? loaded : {}
}

function FlyTo({ position }) {
  const map = useMap()
  useEffect(() => {
    if (position) map.flyTo([position.lat, position.lon], Math.max(map.getZoom(), 13))
  }, [map, position])
  return null
}

function Toggle({ on, onChange, children }) {
  return (
    <button className={on ? 'chip on' : 'chip'} aria-pressed={on} onClick={() => onChange(!on)}>
      <span className="dot" aria-hidden="true" />{children}
    </button>
  )
}

function Legend({ critical, relief, buildings }) {
  const t = useT()
  const { lang } = useLanguage()
  return (
    <details className="card legend">
      <summary><strong>{t('legend')}</strong><ChevronDown className="chev" size={20} aria-hidden="true" /></summary>
      <ul>
        <li><span className="key flood" /> {t('legend_flood')}</li>
        <li><span className="key unknown" /> {t('legend_unknown')}</li>
        <li><span className="key froad" /> ✕ {t('legend_flooded_road')}</li>
        <li><span className="key route" /> ➜ {t('legend_route')}</li>
        <li><span className="vm static" style={{ '--c': STATUS.i.color }}>✕</span>
          <span>{t('legend_village')} ({Object.values(STATUS).map((s) => `${s.symbol} ${t(s.key)}`).join(' · ')})</span></li>
        <li><span className="sm static" /> {t('legend_shelter')}</li>
        {critical && <li><span className="key critical" /> {t('legend_critical')}</li>}
        {relief && <li><span className="rm static" /> {t('legend_relief')}</li>}
        {buildings && <li><span className="bm static" /> {t('legend_buildings', { m: formatNumber(buildings.cell_m, lang) })}</li>}
        <li><span className="me static" /> {t('legend_me')}</li>
      </ul>
    </details>
  )
}

function FloodMap() {
  const t = useT()
  const { lang } = useLanguage()
  const { floodId, flood, dateIndex, village, setVillageId } = useAppState()
  const layers = useLayers(floodId)
  const analysis = useAnalysis(floodId)
  const asked = useLocation().state || {}
  const [show, setShow] = useState({ flood: true, roads: true, routes: true, shelters: true, satellite: false,
    critical: !!asked.critical, relief: !!asked.relief, buildings: !!asked.buildings })
  const [me, setMe] = useState(null)
  const [gpsFailed, setGpsFailed] = useState(false)
  const date = flood.status.dates[dateIndex]
  const bounds = flood.metadata.flood_bounds[date]
  const cov = coverage(flood, dateIndex)
  const set = (key) => (value) => setShow((s) => ({ ...s, [key]: value }))

  const floodedToday = useMemo(() => layers.flooded && {
    ...layers.flooded, features: layers.flooded.features.filter((f) => f.properties.d.includes(dateIndex)) },
  [layers.flooded, dateIndex])
  const criticalToday = useMemo(() => analysis?.roads && {
    type: 'FeatureCollection', features: stretchesOn(analysis.roads, dateIndex) }, [analysis, dateIndex])
  const villageRoutes = useMemo(() => layers.routes && village && {
    ...layers.routes, features: layers.routes.features.filter((f) => f.properties.village_id === village.id) },
  [layers.routes, village])

  async function locate() {
    setGpsFailed(false)
    try {
      setMe(await getPosition())
    } catch {
      setGpsFailed(true)
    }
  }

  return (
    <>
      <div className="chips" role="group" aria-label={t('legend')}>
        <Toggle on={show.flood} onChange={set('flood')}>{t('layer_flood')}</Toggle>
        <Toggle on={show.roads} onChange={set('roads')}>{t('layer_roads')}</Toggle>
        <Toggle on={show.routes} onChange={set('routes')}>{t('layer_routes')}</Toggle>
        <Toggle on={show.shelters} onChange={set('shelters')}>{t('layer_shelters')}</Toggle>
        {analysis?.roads && <Toggle on={show.critical} onChange={set('critical')}>{t('layer_critical')}</Toggle>}
        {analysis?.relief && <Toggle on={show.relief} onChange={set('relief')}>{t('layer_relief')}</Toggle>}
        {analysis?.buildings && <Toggle on={show.buildings} onChange={set('buildings')}>{t('layer_buildings')}</Toggle>}
        <Toggle on={show.satellite} onChange={set('satellite')}>{t('layer_satellite')}</Toggle>
      </div>
      {show.satellite && <p className="muted small">{t('satellite_online')}</p>}
      {gpsFailed && <p className="muted small">{t('gps_failed')}</p>}

      <div className="mapwrap">
        <span className={`map-date ${cov.kind}`} role="status">
          {formatDate(date, lang, true)}
          {cov.kind !== 'full' && <em>{t(`cov_tag_${cov.kind}`)}</em>}
        </span>
        <button className="map-locate" onClick={locate}>
          <LocateFixed size={20} aria-hidden="true" /> {t('my_location')}
        </button>
        <MapContainer key={floodId} className="map" zoomControl attributionControl
          {...(village ? { center: [village.lat, village.lon], zoom: 13 } : { bounds: [bounds[0], bounds[1]] })}>
          {show.satellite && (
            <TileLayer url={SATELLITE} attribution="Imagery: Esri, Maxar, Earthstar Geographics" maxZoom={18} />
          )}
          {layers.area && <GeoJSON data={layers.area} style={AREA} interactive={false} />}
          {layers.roads && (
            <GeoJSON data={layers.roads} interactive={false} attribution="© OpenStreetMap contributors (ODbL)"
              style={(f) => ({ color: ROAD_STYLE[f.properties.c][0], weight: ROAD_STYLE[f.properties.c][1], opacity: 0.9 })} />
          )}
          {show.flood && (
            <ImageOverlay key={`${floodId}-${date}`} url={floodImageUrl(floodId, date)} bounds={bounds} opacity={0.75} />
          )}
          {show.roads && floodedToday && <GeoJSON key={`fr-${dateIndex}`} data={floodedToday} style={FLOODED_ROAD} interactive={false} />}
          {show.buildings && analysis?.buildings && <BuildingsLayer data={analysis.buildings} index={dateIndex} />}
          {show.critical && criticalToday && (
            <GeoJSON key={`cr-${dateIndex}-${lang}`} data={criticalToday} style={CRITICAL}
              onEachFeature={(f, layer) => layer.bindTooltip(t('crit_tip', {
                n: formatNumber(f.properties.villages, lang), p: formatNumber(f.properties.population, lang) }))} />
          )}
          {show.routes && villageRoutes && <GeoJSON key={`rt-${village.id}`} data={villageRoutes} style={ROUTE} interactive={false} />}
          {show.shelters && layers.shelters?.features.map((f, i) => (
            <Marker key={`s${i}`} position={[f.geometry.coordinates[1], f.geometry.coordinates[0]]} icon={SHELTER_ICON}>
              <Tooltip>{f.properties.name} · {t('shelter_unverified')}</Tooltip>
            </Marker>
          ))}
          {show.relief && analysis?.relief?.sites.map((s) => (
            <Marker key={`r-${s.shelter_id}`} position={[s.lat, s.lon]} icon={RELIEF_ICON}>
              <Tooltip>{t('relief_tip', { name: s.name })}</Tooltip>
            </Marker>
          ))}
          {flood.villages.map((v) => {
            const code = statusCode(flood, v.id, dateIndex)
            return (
              <Marker key={v.id} position={[v.lat, v.lon]} icon={villageIcon(code, v.id === village?.id)}
                eventHandlers={{ click: () => setVillageId(v.id) }}>
                <Tooltip>{villageName(v, lang)} · {t(STATUS[code].key)}</Tooltip>
              </Marker>
            )
          })}
          {me && (
            <>
              <Circle center={[me.lat, me.lon]} radius={me.accuracy} pathOptions={{ color: '#102D46', weight: 1, fillOpacity: 0.08 }} />
              <Marker position={[me.lat, me.lon]} icon={ME_ICON}>
                <Tooltip>{t('you_are_here', { m: formatNumber(me.accuracy, lang) })}</Tooltip>
              </Marker>
              <FlyTo position={me} />
            </>
          )}
        </MapContainer>
      </div>

      <div className="map-panel">
        <div className="card">
          <DateSlider />
        </div>
        {village && (
          <div className="card">
            <div className="row spread">
              <strong className="vname">{villageName(village, lang)}</strong>
              <StatusBadge code={statusCode(flood, village.id, dateIndex)} />
            </div>
            {village.route_shelter && <p className="muted small">{t('route_caveat')}</p>}
            <Link className="btn wide" to="/village">{t('details')} <ChevronRight size={18} aria-hidden="true" /></Link>
          </div>
        )}
        <Legend critical={!!analysis?.roads} relief={!!analysis?.relief} buildings={analysis?.buildings} />
        <Link className="btn secondary wide analysis-link" to="/analysis">
          <ChartNoAxesCombined size={18} aria-hidden="true" /> {t('analysis_open')}
        </Link>
      </div>
    </>
  )
}

export default function MapPage() {
  const t = useT()
  return (
    <section>
      <PageHead Icon={MapIcon} title={t('map_title')} sub={t('page_map_sub')} />
      <Loading>
        <FloodBanner />
        <FloodMap />
        <Notice />
      </Loading>
    </section>
  )
}
