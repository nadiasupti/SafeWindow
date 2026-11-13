import { Bell, BellOff, ChevronRight, Siren, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Notice from '../components/Notice.jsx'
import PageHead from '../components/PageHead.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { ALERT_EVENT, clearAlerts, isActive, listAlerts, markSeen } from '../lib/alertStore.js'
import { formatDateTime } from '../lib/format.js'
import { LEVELS } from '../lib/levels.js'
import { useAppState } from '../state/appState.js'

/** Every alert kept on this phone, newest first. Works offline: they are stored in IndexedDB. */
export default function AlertsPage() {
  const t = useT()
  const { lang } = useLanguage()
  const navigate = useNavigate()
  const { setFloodId, setVillageId } = useAppState()
  const [alerts, setAlerts] = useState(null)

  useEffect(() => {
    let alive = true
    const reload = () => listAlerts().then((list) => alive && setAlerts(list)).catch(() => alive && setAlerts([]))
    reload()
    markSeen()                       // opening this page clears the bell's count
    window.addEventListener(ALERT_EVENT, reload)
    return () => {
      alive = false
      window.removeEventListener(ALERT_EVENT, reload)
    }
  }, [])

  function openVillage(a) {
    setFloodId(a.flood)
    setVillageId(a.village)
    navigate('/village')
  }

  async function clearAll() {
    if (!window.confirm(t('alerts_clear_confirm'))) return
    await clearAlerts()
    setAlerts([])
    markSeen()
  }

  return (
    <section>
      <PageHead Icon={Bell} title={t('alerts_page')} sub={t('page_alerts_sub')} />
      {alerts === null && <p className="muted">{t('loading')}</p>}
      {alerts?.length === 0 && (
        <div className="card">
          <p className="row-inline"><BellOff size={18} aria-hidden="true" /> {t('alerts_empty')}</p>
          <p className="muted small">{t('alerts_empty_help')}</p>
        </div>
      )}
      {alerts?.map((a) => {
        const active = isActive(a)
        return (
          <article key={a.id} className={active ? 'card alert-item' : 'card alert-item old'}
            style={{ '--c': LEVELS[a.level]?.color || '#526477' }}>
            <p className="alert-level">
              <Siren size={18} aria-hidden="true" /> {t(`level_${a.level}`)}
              {a.simulation && <span className="sim">{t('simulation')}</span>}
            </p>
            <p><strong>{a.title}</strong></p>
            <p>{a.body}</p>
            <p className="muted small">
              {t('alert_sent', { d: formatDateTime(a.sent_at, lang) || '–' })}
              {' · '}
              {a.cancelled ? t('alert_cancelled') : active ? t('alert_valid_until', { d: formatDateTime(a.expires_at, lang) || '–' }) : t('alert_expired')}
            </p>
            <button className="btn secondary" onClick={() => openVillage(a)}>
              {t('alerts_open_village')} <ChevronRight size={18} aria-hidden="true" />
            </button>
          </article>
        )
      })}
      {alerts?.length > 0 && (
        <>
          <p className="muted small">{t('alerts_kept')}</p>
          <button className="btn secondary wide" onClick={clearAll}>
            <Trash2 size={18} aria-hidden="true" /> {t('alerts_clear')}
          </button>
        </>
      )}
      <Notice />
    </section>
  )
}
