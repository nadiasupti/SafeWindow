import { Bell, BellOff, ChevronRight, Siren } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage, useT } from '../i18n/language.js'
import { ALERT_EVENT, isActive, listAlerts } from '../lib/alertStore.js'
import { formatDateTime } from '../lib/format.js'
import { LEVELS } from '../lib/levels.js'
import { useAppState } from '../state/appState.js'
import AlertSubscribe from './AlertSubscribe.jsx'

/** The latest alert for the chosen village (kept on the phone, so it also shows offline), and the subscribe button. */
export default function AlertCard() {
  const t = useT()
  const { lang } = useLanguage()
  const { floodId, village } = useAppState()
  const [alerts, setAlerts] = useState([])

  // stored alerts now, and again whenever one arrives while the app is open (AlertListener)
  useEffect(() => {
    let alive = true
    const reload = () => listAlerts().then((list) => alive && setAlerts(list)).catch(() => {})
    reload()
    window.addEventListener(ALERT_EVENT, reload)
    return () => {
      alive = false
      window.removeEventListener(ALERT_EVENT, reload)
    }
  }, [])

  const latest = alerts.find((a) => a.flood === floodId && a.village === village?.id)
  const level = latest && LEVELS[latest.level]
  const active = latest && isActive(latest)

  return (
    <div className="card">
      <h2><Bell size={20} aria-hidden="true" /> {t('alert_title')}</h2>
      {latest ? (
        <div className={active ? 'alert' : 'alert old'} style={{ '--c': level?.color || '#526477' }}>
          <p className="alert-level">
            <Siren size={18} aria-hidden="true" /> {t(`level_${latest.level}`)}
            {latest.simulation && <span className="sim">{t('simulation')}</span>}
          </p>
          <p><strong>{latest.title}</strong></p>
          <p>{latest.body}</p>
          <p className="muted small">
            {t('alert_sent', { d: formatDateTime(latest.sent_at, lang) || '–' })}
            {' · '}
            {latest.cancelled ? t('alert_cancelled') : active ? t('alert_valid_until', { d: formatDateTime(latest.expires_at, lang) || '–' }) : t('alert_expired')}
          </p>
        </div>
      ) : (
        <p className="row-inline"><BellOff size={18} aria-hidden="true" /> {t('alert_none')}</p>
      )}
      <Link className="btn link" to="/alerts">{t('alerts_see_all')} <ChevronRight size={16} aria-hidden="true" /></Link>
      <AlertSubscribe />
    </div>
  )
}
