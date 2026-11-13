import { ChartNoAxesCombined, ChevronRight, CloudRain, House, Map as MapIcon, Package, Play, Route, Satellite } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import DateSlider from '../components/DateSlider.jsx'
import FloodBanner from '../components/FloodBanner.jsx'
import Loading from '../components/Loading.jsx'
import Notice from '../components/Notice.jsx'
import PageHead from '../components/PageHead.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { coverage } from '../lib/coverage.js'
import { formatDate, formatDateTime, formatNumber } from '../lib/format.js'
import { villageName } from '../lib/village.js'
import { dryStretches, isFragile, stretchesOn, useAnalysis } from '../services/analysis.js'
import { DATA_BASE } from '../services/data.js'
import { useAppState } from '../state/appState.js'

function useNames() {
  const { lang } = useLanguage()
  const { flood } = useAppState()
  const byId = Object.fromEntries(flood.villages.map((v) => [v.id, v]))
  return (ids) => ids.map((id) => (byId[id] ? villageName(byId[id], lang) : id)).join(', ')
}

function Replay() {
  const t = useT()
  const navigate = useNavigate()
  return (
    <div className="card">
      <h2><Play size={20} aria-hidden="true" /> {t('replay_title')}</h2>
      <p>{t('replay_text')}</p>
      <button className="btn wide" onClick={() => navigate('/map')}>
        <MapIcon size={18} aria-hidden="true" /> {t('replay_open')}
      </button>
    </div>
  )
}

function StretchList({ items }) {
  const t = useT()
  const { lang } = useLanguage()
  const names = useNames()
  return (
    <ol className="urgent">
      {items.map((f, i) => (
        <li key={i}>
          <span className="row-inline"><span className="rank">{formatNumber(i + 1, lang)}</span>
            <span>{t(f.properties.buildings != null ? 'crit_item_b' : 'crit_item', { names: names(f.properties.village_ids),
              p: formatNumber(f.properties.population, lang), km: formatNumber(f.properties.length_m / 1000, lang, 1),
              b: formatNumber(f.properties.buildings ?? 0, lang) })}</span>
          </span>
        </li>
      ))}
    </ol>
  )
}

function Criticality({ analysis }) {
  const t = useT()
  const { lang } = useLanguage()
  const navigate = useNavigate()
  const { flood, dateIndex } = useAppState()
  const { critical, roads } = analysis
  const date = flood.status.dates[dateIndex]
  const today = stretchesOn(roads, dateIndex)
  const fragile = flood.villages.filter((v) => isFragile(critical, v.id, dateIndex))
  const people = fragile.reduce((s, v) => s + (v.population || 0), 0)
  const dry = dryStretches(roads)
  const noRadar = coverage(flood, dateIndex).kind === 'none'
  return (
    <div className="card">
      <h2><Route size={20} aria-hidden="true" /> {t('crit_title')}</h2>
      <p className="muted small">{t('crit_what')}</p>
      <DateSlider />
      <h3 className="sub-title">{t('crit_on_date', { d: formatDate(date, lang, true) })}</h3>
      {noRadar ? <p>{t('crit_no_radar')}</p> : fragile.length > 0 ? (
        <>
          <p><strong>{t('crit_fragile', { n: formatNumber(fragile.length, lang), p: formatNumber(people, lang) })}</strong></p>
          <StretchList items={today.slice(0, 5)} />
        </>
      ) : <p>{t('crit_none_on_date')}</p>}
      <button className="btn secondary wide" onClick={() => navigate('/map', { state: { critical: true } })}>
        <MapIcon size={18} aria-hidden="true" /> {t('crit_see_map')}
      </button>
      <h3 className="sub-title">{t('crit_dry_title')}</h3>
      {dry.length ? <StretchList items={dry.slice(0, 5)} /> : <p>{t('crit_dry_none')}</p>}
      <p className="notice small">{t('crit_limits')}</p>
    </div>
  )
}

function Relief({ relief }) {
  const t = useT()
  const { lang } = useLanguage()
  const navigate = useNavigate()
  const { floods } = useAppState()
  // a flood by its year ("2022"), in the reader's digits: shorter than the full flood name inside a sentence
  const nameOf = (id) => {
    const first = floods?.find((f) => f.id === id)?.first_date
    return first ? new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD' : 'en-GB', { year: 'numeric', timeZone: 'UTC' })
      .format(new Date(`${first}T00:00:00Z`)) : id
  }
  const n = (x) => formatNumber(x, lang)
  const tt = relief.test
  const vars = { train: nameOf(relief.train_flood), test: nameOf(relief.test_flood), k: n(relief.k), r: n(relief.radius_km) }
  return (
    <div className="card">
      <div className="card-head">
        <h2><Package size={20} aria-hidden="true" /> {t('relief_title')}</h2>
      </div>
      <p><span className="pill amber">{t('relief_badge')}</span></p>
      <p>{t('relief_what', vars)}</p>
      <div className="estimate">
        <p className="estimate-label">{t('relief_result', { ...vars, v: n(tt.villages), c: n(tt.covered_villages),
          pc: n(tt.covered_people), pt: n(tt.people) })}</p>
        <p className="small">{t('relief_yardstick', { k: n(relief.k), rand: n(tt.random_mean_people),
          best: tt.best_possible_people == null ? '–' : n(tt.best_possible_people) })}</p>
      </div>
      {tt.same_villages_as_train && <p className="notice small">{t('relief_same')}</p>}

      <h3 className="sub-title">{t('relief_sites')}</h3>
      <ol className="urgent">
        {relief.sites.map((s, i) => (
          <li key={s.shelter_id}>
            <span className="row-inline"><span className="rank">{n(i + 1)}</span>{s.name}</span>
            <span className="pill grey">{t('shelter_unverified')}</span>
          </li>
        ))}
      </ol>

      <h3 className="sub-title">{t('relief_villages', vars)}</h3>
      <ul className="plain">
        {tt.village_rows.map((v) => (
          <li key={v.village_id} className="relief-row">
            <span className="row-inline" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <strong>{(lang === 'bn' && v.name_bn) || v.name}</strong>
              <span className={v.covered ? 'pill' : 'pill grey'}>{t(v.covered ? 'relief_in' : 'relief_out', vars)}</span>
            </span>
            <span className="muted small">{t('relief_row', { km: v.nearest_site_km == null ? '–' : formatNumber(v.nearest_site_km, lang, 1),
              d: formatDate(v.last_connected, lang) })}</span>
          </li>
        ))}
      </ul>

      <details className="stage">
        <summary>{t('relief_radius')}</summary>
        <ul>
          {relief.sensitivity.map((s) => (
            <li key={s.radius_km}>{t('relief_radius_row', { r: n(s.radius_km), p: n(s.test_people_covered), rand: n(s.random_mean_people) })}</li>
          ))}
        </ul>
      </details>
      <p className="muted small">{t('relief_timing')}</p>
      <button className="btn secondary wide" onClick={() => navigate('/map', { state: { relief: true } })}>
        <MapIcon size={18} aria-hidden="true" /> {t('crit_see_map')}
      </button>
    </div>
  )
}

function ReliefElsewhere() {
  const t = useT()
  const { floods, floodId, setFloodId } = useAppState()
  const other = floods?.find((f) => f.id !== floodId && f.analyses?.relief)
  if (!other) return null
  return (
    <div className="card soft">
      <h2><Package size={20} aria-hidden="true" /> {t('relief_title')}</h2>
      <p>{t('relief_elsewhere', { name: other.name })}</p>
      <button className="btn secondary" onClick={() => setFloodId(other.id)}>
        {t('relief_switch')} <ChevronRight size={18} aria-hidden="true" />
      </button>
    </div>
  )
}

/** What the daily check (GitHub Actions, scripts/daily_check.py) last found: radar dates and NASA GPM rain only. */
function DailyWatch() {
  const t = useT()
  const { lang } = useLanguage()
  const [watch, setWatch] = useState(null)
  useEffect(() => {
    let alive = true
    fetch(`${DATA_BASE}/monitor.json`)
      .then((r) => (r.ok && (r.headers.get('content-type') || '').includes('json') ? r.json() : null))
      .then((m) => alive && setWatch(m))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])
  if (!watch?.regions?.length) return null
  const mm = (v) => (v == null ? '–' : formatNumber(v, lang, 1))
  const box = (name) => name.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())
  return (
    <div className="card">
      <h2><CloudRain size={20} aria-hidden="true" /> {t('monitor_title')}</h2>
      <p className="muted small">{t('monitor_text')}</p>
      {watch.regions.map((r) => (
        <div key={r.region} className="watch-region">
          <h3 className="sub-title">{r.name}</h3>
          <p className="small">{t('monitor_checked', { d: formatDateTime(r.checked_at, lang) || '–' })}</p>
          <p className="small">{t('monitor_radar', { d: r.newest_radar ? formatDate(r.newest_radar, lang, true) : '–' })}
            {' · '}{t('monitor_new', { n: formatNumber((r.new_since_last_check || []).length, lang) })}</p>
          {r.rain && Object.keys(r.rain).length ? (
            <ul className="plain small">
              {Object.entries(r.rain).map(([name, v]) => (
                <li key={name}>{t('monitor_rain', { box: box(name), a: mm(v['1d_mm']), b: mm(v['3d_mm']), c: mm(v['7d_mm']),
                  d: v.through ? formatDate(v.through, lang) : '–' })}</li>
              ))}
            </ul>
          ) : <p className="small">{t('monitor_rain_none')}</p>}
        </div>
      ))}
      <p className="notice small">{t('monitor_period')}</p>
    </div>
  )
}

function NisarLink() {
  const t = useT()
  const navigate = useNavigate()
  return (
    <div className="card">
      <h2><Satellite size={20} aria-hidden="true" /> {t('nisar_title')}</h2>
      <p>{t('nisar_open_sub')}</p>
      <button className="btn wide" onClick={() => navigate('/nisar')}>
        <Satellite size={18} aria-hidden="true" /> {t('nisar_open')}
      </button>
    </div>
  )
}

/** Mapped buildings on the chosen radar date, and the settlements to check first in the field. */
function Buildings({ data }) {
  const t = useT()
  const { lang } = useLanguage()
  const navigate = useNavigate()
  const { flood, dateIndex } = useAppState()
  const byId = Object.fromEntries(flood.villages.map((v) => [v.id, v]))
  const n = (v) => formatNumber(v, lang)
  const date = flood.status.dates[dateIndex]
  const tot = data.totals.find((x) => x.date === date)
  const noRadar = coverage(flood, dateIndex).kind === 'none'
  return (
    <div className="card">
      <h2><House size={20} aria-hidden="true" /> {t('bld_title')}</h2>
      <p className="muted small">{t('bld_what', { n: n(data.buildings) })}</p>
      <DateSlider />
      <h3 className="sub-title">{t('bld_on_date', { d: formatDate(date, lang, true) })}</h3>
      {noRadar ? <p>{t('crit_no_radar')}</p> : tot && (
        <ul className="plain">
          <li><strong>{t('bld_isolated', { n: n(tot.isolated) })}</strong></li>
          <li>{t('bld_uncertain', { n: n(tot.uncertain) })}</li>
          <li>{t('bld_near', { n: n(tot.near_water) })}</li>
          <li>{t('bld_far', { n: n(tot.far_from_roads) })}</li>
          {tot.no_road_link > 0 && <li>{t('bld_no_link', { n: n(tot.no_road_link) })}</li>}
        </ul>
      )}
      <button className="btn secondary wide" onClick={() => navigate('/map', { state: { buildings: true } })}>
        <MapIcon size={18} aria-hidden="true" /> {t('bld_open')}
      </button>
      <h3 className="sub-title">{t('bld_priority_title')}</h3>
      {data.clusters.length ? (
        <ol className="urgent">
          {data.clusters.slice(0, 5).map((c) => (
            <li key={c.rank}>
              <span className="row-inline"><span className="rank">{n(c.rank)}</span>
                <span>{t('bld_cluster', { v: byId[c.nearest_village_id] ? villageName(byId[c.nearest_village_id], lang) : '–',
                  km: formatNumber(c.nearest_village_km, lang, 1), m: n(data.cell_m), b: n(c.buildings), i: n(c.max_isolated),
                  n: n(c.dates_isolated), d: formatDate(c.first_isolated, lang) })}
                <span className="muted small coords">{t('bld_gps', { lat: c.lat.toFixed(4), lon: c.lon.toFixed(4) })}</span></span>
              </span>
            </li>
          ))}
        </ol>
      ) : <p>{t('bld_none_isolated')}</p>}
      <p className="muted small">{t('bld_priority_how')}</p>
      <p className="notice small">{t('bld_limits')}</p>
    </div>
  )
}

function Sections() {
  const t = useT()
  const { floodId } = useAppState()
  const analysis = useAnalysis(floodId)
  return (
    <>
      <FloodBanner />
      <Replay />
      <NisarLink />
      {analysis === null && <p className="muted">{t('loading')}</p>}
      {analysis?.critical && analysis?.roads && <Criticality analysis={analysis} />}
      {analysis?.buildings && <Buildings data={analysis.buildings} />}
      {analysis && (analysis.relief ? <Relief relief={analysis.relief} /> : <ReliefElsewhere />)}
      <DailyWatch />
      <Notice />
    </>
  )
}

export default function AnalysisPage() {
  const t = useT()
  return (
    <section>
      <PageHead Icon={ChartNoAxesCombined} title={t('analysis_title')} sub={t('analysis_sub')} />
      <Loading>
        <Sections />
      </Loading>
    </section>
  )
}
