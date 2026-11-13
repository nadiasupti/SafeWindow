import {
  BatteryCharging, CalendarCheck, ChartNoAxesCombined, CalendarDays, CalendarX, ChevronDown, ChevronRight, CircleCheck, CircleHelp,
  Download, Hourglass, House, Images, Map as MapIcon, MapPin, Package, Radio, ScanSearch, Ship, Siren, TriangleAlert,
  Satellite, Users,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import AlertCard from '../components/AlertCard.jsx'
import DateSlider from '../components/DateSlider.jsx'
import FloodBanner from '../components/FloodBanner.jsx'
import OfficialAlerts from '../components/OfficialAlerts.jsx'
import FloodSelect from '../components/FloodSelect.jsx'
import HeroArt from '../components/HeroArt.jsx'
import Loading from '../components/Loading.jsx'
import Notice from '../components/Notice.jsx'
import OfflineCard from '../components/OfflineCard.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import VillagePicker from '../components/VillagePicker.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { formatDate, formatNumber } from '../lib/format.js'
import { STATUS, rankedIsolated, statusCode, supplyEstimate, villageName } from '../lib/village.js'
import { useAppState } from '../state/appState.js'

// Each status has its own icon shape too, so the card reads without colour.
const STATUS_ICON = { c: CircleCheck, i: TriangleAlert, u: CircleHelp, b: Ship }

function Waves() {
  return (
    <svg className="waves" viewBox="0 0 400 56" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 30 C 50 18, 90 42, 140 30 S 230 18, 280 30 S 360 42, 400 28 V56 H0Z" fill="rgba(255,255,255,0.12)" />
      <path d="M0 40 C 60 30, 100 50, 160 40 S 260 30, 320 40 S 380 48, 400 40 V56 H0Z" fill="var(--bg)" />
    </svg>
  )
}

function Hero({ onChange }) {
  const t = useT()
  const { lang } = useLanguage()
  const { village } = useAppState()
  return (
    <div className="hero-band">
      <div className="hero-top">
        <div>
          <p className="hero-sub">{t('tagline')}</p>
          <span className="hero-tag">{t('research_tool')}</span>
        </div>
        <HeroArt />
      </div>
      <FloodSelect />
      {village && (
        <>
          <button className="village-pill" onClick={onChange}>
            <MapPin size={20} aria-hidden="true" />
            <span className="vp-name">{villageName(village, lang)}</span>
            <span className="vp-change">{t('change_village')}</span>
            <ChevronDown size={18} aria-hidden="true" />
          </button>
        </>
      )}
      <Waves />
    </div>
  )
}

/** The village's status on the chosen radar date, large: icon + word + colour, and what it means. */
function StatusCard() {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, village, dateIndex } = useAppState()
  const code = statusCode(flood, village.id, dateIndex)
  const s = STATUS[code] || STATUS.u
  const Icon = STATUS_ICON[code] || CircleHelp
  return (
    <div className="status-card" style={{ '--c': s.color }}>
      <span className="status-icon" aria-hidden="true"><Icon size={34} strokeWidth={2.2} /></span>
      <div>
        <p className="status-when">{t('status_on', { d: formatDate(flood.status.dates[dateIndex], lang, true) })}</p>
        <p className="status-word">{t(s.key)}</p>
        <p className="status-text">{t(`outcome_${village.outcome}`)}</p>
      </div>
      <div className="status-actions">
        <Link className="btn" to="/village">{t('details')} <ChevronRight size={18} aria-hidden="true" /></Link>
        <Link className="btn secondary" to="/map"><MapIcon size={18} aria-hidden="true" /> {t('view_on_map')}</Link>
      </div>
    </div>
  )
}

function Stat({ Icon, tone, label, value, tag }) {
  return (
    <div className={tone ? `stat ${tone}` : 'stat'}>
      <Icon size={26} aria-hidden="true" />
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {tag && <span className="pill amber">{tag}</span>}
    </div>
  )
}

/** Three key facts from the data: the observed dates for an isolated village, otherwise the radar image counts. */
function KeyStats() {
  const t = useT()
  const { lang } = useLanguage()
  const { village: v, supplyDays } = useAppState()
  const images = (n) => t('stat_images', { n: formatNumber(n ?? 0, lang) })
  if (v.outcome === 'isolated') {
    return (
      <div className="stats">
        <Stat Icon={CalendarCheck} tone="green" label={t('stat_last_passable')}
          value={v.last_connected ? formatDate(v.last_connected, lang) : '–'} />
        <Stat Icon={CalendarX} tone="red" label={t('stat_first_isolated')} value={formatDate(v.first_isolated, lang)} />
        <Stat Icon={Hourglass} tone="amber" label={t('stat_supply')}
          value={formatDate(supplyEstimate(v, supplyDays), lang)} tag={t('estimate_tag')} />
      </div>
    )
  }
  return (
    <div className="stats">
      <Stat Icon={CircleCheck} tone="green" label={t('stat_seen_connected')} value={images(v.n_dates_connected)} />
      <Stat Icon={TriangleAlert} tone="red" label={t('stat_seen_isolated')} value={images(v.n_dates_isolated)} />
      <Stat Icon={ScanSearch} tone="amber" label={t('stat_not_seen')} value={images(v.n_dates_uncertain)} />
    </div>
  )
}

function QuickLinks() {
  const t = useT()
  const items = [
    { to: '/map', key: 'quick_map', Icon: MapIcon },
    { to: '/village', key: 'quick_village', Icon: House },
    { to: '/emergency', key: 'quick_emergency', Icon: Siren, tone: 'red' },
    { href: '#offline', key: 'quick_offline', Icon: Download },
  ]
  return (
    <nav className="quick-grid" aria-label={t('quick_label')}>
      {items.map(({ to, href, key, Icon, tone }) => {
        const inner = (
          <>
            <span className="quick-icon" aria-hidden="true"><Icon size={24} /></span>
            <span className="quick-text">{t(key)}</span>
            <ChevronRight size={18} aria-hidden="true" />
          </>
        )
        const cls = tone ? `quick ${tone}` : 'quick'
        return to
          ? <Link key={key} className={cls} to={to}>{inner}</Link>
          : <a key={key} className={cls} href={href}>{inner}</a>
      })}
    </nav>
  )
}

function WhatToDo() {
  const t = useT()
  const { lang } = useLanguage()
  const { supplyDays } = useAppState()
  const steps = [
    { Icon: BatteryCharging, text: t('todo_charge') },
    { Icon: Package, text: t('todo_food', { n: formatNumber(supplyDays, lang) }) },
    { Icon: Radio, text: t('todo_official') },
    { Icon: Users, text: t('todo_local') },
  ]
  return (
    <div className="card">
      <h2>{t('todo_title')}</h2>
      <ul className="todo">
        {steps.map(({ Icon, text }) => (
          <li key={text}><span className="todo-icon" aria-hidden="true"><Icon size={24} /></span>{text}</li>
        ))}
      </ul>
      <Link className="btn link" to="/emergency">{t('todo_more')} <ChevronRight size={16} aria-hidden="true" /></Link>
    </div>
  )
}

/** The whole flood area on the chosen date: how many villages were seen isolated, most urgent first. */
function AreaSummary() {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, dateIndex } = useAppState()
  const date = flood.status.dates[dateIndex]
  const isolated = flood.villages.filter((v) => statusCode(flood, v.id, dateIndex) === 'i')
  const people = isolated.reduce((sum, v) => sum + (v.population || 0), 0)
  const urgent = rankedIsolated(flood.villages).slice(0, 5)
  return (
    <div className="card">
      <h2><Images size={20} aria-hidden="true" /> {t('area_title')}</h2>
      <DateSlider />
      <p><strong>{t('isolated_summary', {
        d: formatDate(date, lang), n: formatNumber(isolated.length, lang), p: formatNumber(people, lang) })}</strong></p>
      {urgent.length > 0 && (
        <>
          <h2>{t('most_urgent')}</h2>
          <ol className="urgent">
            {urgent.map((v, i) => (
              <li key={v.id}>
                <span className="row-inline"><span className="rank">{formatNumber(i + 1, lang)}</span>{villageName(v, lang)}</span>
                <StatusBadge code={statusCode(flood, v.id, dateIndex)} />
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}

function Freshness() {
  const t = useT()
  const { lang } = useLanguage()
  const { metadata } = useAppState().flood
  return (
    <p className="fresh">
      <CalendarDays size={18} aria-hidden="true" />
      <span>{t('radar_date')}: <strong>{formatDate(metadata.observed_through, lang, true)}</strong></span>
      <Link className="btn link" to="/settings">{t('fresh_more')}</Link>
    </p>
  )
}

export default function HomePage() {
  const t = useT()
  const { village } = useAppState()
  const [picking, setPicking] = useState(false)
  const showVillage = village && !picking
  return (
    <section>
      <h1 className="sr-only">{t('home_title')}</h1>
      <Loading>
        <Hero onChange={() => setPicking(true)} />
        <div className="hero-lift">
          <FloodBanner />
          <OfficialAlerts />
          {showVillage ? (
            <>
              <StatusCard />
              <KeyStats />
            </>
          ) : (
            <div className="card">
              <div className="card-head">
                <h2><MapPin size={20} aria-hidden="true" /> {t('pick_village')}</h2>
                {village && <button className="btn link" onClick={() => setPicking(false)}>{t('cancel')}</button>}
              </div>
              <VillagePicker onPicked={() => setPicking(false)} />
            </div>
          )}
          <QuickLinks />
          <Link className="analysis-card" to="/analysis">
            <span className="quick-icon" aria-hidden="true"><ChartNoAxesCombined size={24} /></span>
            <span><strong>{t('analysis_open')}</strong><span className="small">{t('analysis_open_sub')}</span></span>
            <ChevronRight size={20} aria-hidden="true" />
          </Link>
          <Link className="analysis-card nisar" to="/nisar">
            <span className="quick-icon" aria-hidden="true"><Satellite size={24} /></span>
            <span><strong>{t('nisar_open')}</strong><span className="small">{t('nisar_open_sub')}</span></span>
            <ChevronRight size={20} aria-hidden="true" />
          </Link>
          <AlertCard />
          <WhatToDo />
          <AreaSummary />
          <div id="offline"><OfflineCard /></div>
          <Freshness />
          <Notice />
        </div>
      </Loading>
    </section>
  )
}
