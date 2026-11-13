import { Bell, ChevronDown, Copy, Download, Languages, LocateFixed, MapPin, Package, Settings, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AlertSubscribe from '../components/AlertSubscribe.jsx'
import FloodSelect from '../components/FloodSelect.jsx'
import Loading from '../components/Loading.jsx'
import OfflineCard from '../components/OfflineCard.jsx'
import PageHead from '../components/PageHead.jsx'
import TimesCard from '../components/TimesCard.jsx'
import VillagePicker from '../components/VillagePicker.jsx'
import { LANGUAGES, useLanguage, useT } from '../i18n/language.js'
import { formatNumber } from '../lib/format.js'
import { gpsPermission } from '../lib/gps.js'
import { villageName } from '../lib/village.js'
import { useInstallPrompt } from '../lib/install.js'
import { alertsAvailability, deviceId } from '../services/alerts.js'
import { useAppState } from '../state/appState.js'

/** Notifications for the chosen village, and this phone's anonymous id (to register it as a test phone). */
function Notifications() {
  const t = useT()
  const [id, setId] = useState(null)
  const [state, setState] = useState('idle')       // idle | loading | ready | unavailable
  const [copied, setCopied] = useState(false)

  async function show() {
    if (id) return
    setState('loading')
    if ((await alertsAvailability()) !== 'ready') {
      setState('unavailable')
      return
    }
    try {
      setId(await deviceId())
      setState('ready')
    } catch {
      setId(null)
      setState('unavailable')
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(id)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="card">
      <h2><Bell size={20} aria-hidden="true" /> {t('notif_title')}</h2>
      <AlertSubscribe />
      <details className="device-box">
        <summary className="device-summary" onClick={show}>
          <span className="device-icon"><Smartphone size={20} aria-hidden="true" /></span>
          <span className="device-text">
            <strong>{t('device_id_title')}</strong>
            <small>{t('device_id_tap')}</small>
          </span>
          <ChevronDown size={20} className="chev" aria-hidden="true" />
        </summary>
        <div className="device-body">
          <p className="muted small">{t('device_id_help')}</p>
          {state === 'loading' && <p className="small">{t('device_id_loading')}</p>}
          {state === 'unavailable' && <p className="small">{t('device_id_unavailable')}</p>}
          {id && (
            <div className="row">
              <code className="device-id">{id}</code>
              <button className="btn secondary" onClick={copy}><Copy size={16} aria-hidden="true" /> {copied ? t('copied') : t('copy')}</button>
            </div>
          )}
        </div>
      </details>
    </div>
  )
}

function Language() {
  const t = useT()
  const { lang, setLang } = useLanguage()
  return (
    <div className="card">
      <h2><Languages size={20} aria-hidden="true" /> {t('language')}</h2>
      <div className="segmented" role="radiogroup" aria-label={t('language')}>
        {LANGUAGES.map((l) => (
          <button key={l.code} role="radio" aria-checked={lang === l.code}
            className={lang === l.code ? 'seg active' : 'seg'} onClick={() => setLang(l.code)}>
            {l.name}
          </button>
        ))}
      </div>
    </div>
  )
}

function Village() {
  const t = useT()
  const { lang } = useLanguage()
  const { village } = useAppState()
  const [open, setOpen] = useState(false)
  return (
    <div className="card">
      <h2><MapPin size={20} aria-hidden="true" /> {t('nav_village')}</h2>
      <FloodSelect />
      <div className="row spread">
        <strong className="vname">{village ? villageName(village, lang) : t('no_village')}</strong>
        <button className="btn link" onClick={() => setOpen(!open)}>{t('change')}</button>
      </div>
      {open && <VillagePicker onPicked={() => setOpen(false)} />}
    </div>
  )
}

function Supply() {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, supplyDays, setSupplyDays } = useAppState()
  const [lo, hi] = flood.metadata.supply_days_range || [2, 14]
  return (
    <div className="card">
      <h2><Package size={20} aria-hidden="true" /> {t('supply_title')}</h2>
      <label className="field-label" htmlFor="supply">
        <span className="pill">{t('supply_value', { n: formatNumber(supplyDays, lang) })}</span>
      </label>
      <input id="supply" type="range" min={lo} max={hi} value={supplyDays}
        onChange={(e) => setSupplyDays(Number(e.target.value))} />
    </div>
  )
}

function Gps() {
  const t = useT()
  const [state, setState] = useState('unknown')
  useEffect(() => {
    gpsPermission().then(setState)
  }, [])
  return (
    <div className="card">
      <h2><LocateFixed size={20} aria-hidden="true" /> {t('gps_title')}</h2>
      <p>{t(`gps_${state}`)}</p>
      <p className="muted small">{t('gps_private')}</p>
    </div>
  )
}

function Install() {
  const t = useT()
  const prompt = useInstallPrompt()
  return (
    <div className="card">
      <h2><Download size={20} aria-hidden="true" /> {t('install_title')}</h2>
      {prompt ? <button className="btn wide" onClick={prompt}>{t('install_btn')}</button> : <p>{t('install_hint')}</p>}
    </div>
  )
}

export default function SettingsPage() {
  const t = useT()
  return (
    <section>
      <PageHead Icon={Settings} title={t('settings_title')} sub={t('page_settings_sub')} />
      <h2 className="setting-group-title">{t('group_general')}</h2>
      <Language />
      <div className="card">
        <h2>{t('rp_account_title')}</h2>
        <p className="muted small">{t('rp_settings_account_note')}</p>
        <div className="row">
          <Link className="btn secondary" to="/account">{t('rp_sign_in')}</Link>
          <Link className="btn secondary" to="/rescue">{t('rp_open_citizen')}</Link>
          <Link className="btn secondary" to="/ngo">{t('rp_open_ngo')}</Link>
        </div>
      </div>
      <Loading>
        <Village />
        <Supply />
        <h2 className="setting-group-title">{t('group_data')}</h2>
        <OfflineCard />
        <TimesCard />
        <h2 className="setting-group-title">{t('group_phone')}</h2>
        <Notifications />
        <Gps />
        <Install />
      </Loading>
    </section>
  )
}
