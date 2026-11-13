import { House, MapPin, Network, Printer, Route, Users } from 'lucide-react'
import { useState } from 'react'
import DateSlider from '../components/DateSlider.jsx'
import FloodBanner from '../components/FloodBanner.jsx'
import Loading from '../components/Loading.jsx'
import Notice from '../components/Notice.jsx'
import PageHead from '../components/PageHead.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import VillagePicker from '../components/VillagePicker.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { daysBetween, formatDate, formatNumber } from '../lib/format.js'
import { STATUS, statusCode, supplyEstimate, villageName } from '../lib/village.js'
import { dryStretches, isFragile, useAnalysis } from '../services/analysis.js'
import { coverage } from '../lib/coverage.js'
import { useAppState } from '../state/appState.js'

function Step({ dot, tone, label, value }) {
  return (
    <li className="step">
      <span className={tone === 'range' ? 'step-dot range' : 'step-dot'}
        style={tone && tone !== 'range' ? { '--c': STATUS[tone].color } : undefined} aria-hidden="true">{dot}</span>
      <div>
        <p className="step-label">{label}</p>
        <p className="step-value">{value}</p>
      </div>
    </li>
  )
}

/** The observed dates of an isolated village, in the plan's wording (section 4), as a timeline. */
function IsolationFacts({ v }) {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, dateIndex, supplyDays } = useAppState()
  const date = flood.status.dates[dateIndex]
  const estimate = supplyEstimate(v, supplyDays)
  const range = v.last_connected
    ? t('window_between', { a: formatDate(v.isolated_from_earliest, lang), b: formatDate(v.first_isolated, lang) })
    : t('window_by', { b: formatDate(v.first_isolated, lang) })

  let countdown
  if (date < v.isolated_from_earliest) countdown = t('not_yet', { d: formatDate(date, lang) })
  else {
    const left = daysBetween(date, estimate)
    countdown = left >= 0
      ? t('days_left', { d: formatDate(date, lang), n: formatNumber(left, lang) })
      : t('days_over', { d: formatDate(date, lang), n: formatNumber(-left, lang) })
  }

  return (
    <div className="card">
      <h2>{t('observations')}</h2>
      <ol className="steps">
        <Step dot="✓" tone="c" label={t('last_connected')}
          value={v.last_connected ? formatDate(v.last_connected, lang, true) : t('last_connected_none')} />
        <Step dot="?" tone="range" label={t('isolation_window')} value={range} />
        <Step dot="✕" tone="i" label={t('first_isolated')} value={formatDate(v.first_isolated, lang, true)} />
        {v.reconnected && <Step dot="✓" tone="c" label={t('reconnected')} value={formatDate(v.reconnected, lang, true)} />}
      </ol>
      <p className="muted small">{t('radar_gap')}</p>
      <div className="estimate">
        <p className="estimate-label">⏳ {t('supply_estimate')}</p>
        <p className="estimate-date">{formatDate(estimate, lang, true)}</p>
        <p>{countdown}</p>
        <p className="muted small">{t('supply_note', { n: formatNumber(supplyDays, lang) })}</p>
      </div>
    </div>
  )
}

function RouteCard({ v }) {
  const t = useT()
  const { lang } = useLanguage()
  return (
    <div className="card">
      <h2><Route size={20} aria-hidden="true" /> {t('route_title')}</h2>
      <div className="route-box">
        <span className="route-icon" aria-hidden="true"><House size={22} /></span>
        <div>
          {v.route_shelter ? (
            <>
              <p>{t('route_text', { s: v.route_shelter, km: formatNumber(v.route_m / 1000, lang, 1),
                d: formatDate(v.last_connected, lang) })}</p>
              <p className="row-inline" style={{ flexWrap: 'wrap' }}>
                <span className="pill amber">{t('not_field_checked')}</span>
                <span className="pill grey">{t('shelter_unverified')}</span>
              </p>
            </>
          ) : <p>{t('route_none')}</p>}
        </div>
      </div>
      <p className="muted small">{t('route_caveat')}</p>
    </div>
  )
}

/** Whether, on the chosen date, the village hung on a single road (scripts/road_criticality.py). */
function RoadDependence({ v }) {
  const t = useT()
  const { lang } = useLanguage()
  const { floodId, flood, dateIndex } = useAppState()
  const analysis = useAnalysis(floodId)
  if (!analysis?.critical || !analysis.roads || v.boat_dependent) return null
  const date = formatDate(flood.status.dates[dateIndex], lang)
  const code = statusCode(flood, v.id, dateIndex)
  const dryKm = dryStretches(analysis.roads)
    .filter((f) => f.properties.village_ids.includes(v.id))
    .reduce((s, f) => s + f.properties.length_m, 0) / 1000
  let line = null
  if (isFragile(analysis.critical, v.id, dateIndex)) line = t('crit_village_fragile', { d: date })
  else if (code === 'c' && coverage(flood, dateIndex).kind !== 'none') line = t('crit_village_ok', { d: date })
  if (!line && dryKm === 0) return null
  return (
    <div className="card">
      <h2><Network size={20} aria-hidden="true" /> {t('road_dependence')}</h2>
      {line && <p>{line}</p>}
      {dryKm > 0 && <p>{t('crit_village_dry', { km: formatNumber(dryKm, lang, 1) })}</p>}
      <p className="muted small">{t('crit_limits')}</p>
    </div>
  )
}

function Timeline({ v }) {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, dateIndex, setDateIndex } = useAppState()
  return (
    <div className="card">
      <h2>{t('timeline')}</h2>
      <ol className="timeline">
        {flood.status.dates.map((d, i) => {
          const code = statusCode(flood, v.id, i)
          return (
            <li key={d}>
              <button className={i === dateIndex ? 'tl active' : 'tl'} style={{ '--c': STATUS[code].color }}
                onClick={() => setDateIndex(i)} aria-label={`${formatDate(d, lang)}: ${t(STATUS[code].key)}`}>
                <span className="tl-symbol" aria-hidden="true">{STATUS[code].symbol}</span>
                <span className="tl-date">{formatDate(d, lang)}</span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="tl-legend" aria-hidden="true">
        {Object.values(STATUS).map((s) => (
          <span key={s.key}><i style={{ '--c': s.color }}>{s.symbol}</i>{t(s.key)}</span>
        ))}
      </p>
    </div>
  )
}

export default function VillagePage() {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, village, dateIndex } = useAppState()
  const [changing, setChanging] = useState(false)
  const code = village && flood ? statusCode(flood, village.id, dateIndex) : 'u'

  return (
    <section>
      <PageHead Icon={House} title={t('village_title')} sub={t('page_village_sub')} />
      <Loading>
        <FloodBanner />
        {!village || changing ? (
          <div className="card">
            <h2><MapPin size={20} aria-hidden="true" /> {t('pick_village')}</h2>
            <VillagePicker onPicked={() => setChanging(false)} />
          </div>
        ) : (
          <>
            <div className="card hero" style={{ borderTopColor: STATUS[code].color }}>
              <div className="row spread">
                <h2 className="village-name">{villageName(village, lang)}</h2>
                <button className="btn link noprint" onClick={() => setChanging(true)}>{t('change')}</button>
              </div>
              <StatusBadge code={code} large />
              <p>{t(`outcome_${village.outcome}`)}</p>
              {village.outcome === 'connected_when_seen' && (
                <p className="muted small">{t('seen_detail', {
                  c: formatNumber(village.n_dates_connected, lang), u: formatNumber(village.n_dates_uncertain, lang) })}</p>
              )}
              <p className="row-inline muted small"><Users size={16} aria-hidden="true" /> {t('population')}: {formatNumber(village.population, lang)}</p>
              <DateSlider />
            </div>
            {village.outcome === 'isolated' && <IsolationFacts v={village} />}
            <RouteCard v={village} />
            <RoadDependence v={village} />
            <Timeline v={village} />
            <button className="btn secondary wide noprint" onClick={() => window.print()}>
              <Printer size={18} aria-hidden="true" /> {t('print_card')}
            </button>
          </>
        )}
        <Notice />
      </Loading>
    </section>
  )
}
