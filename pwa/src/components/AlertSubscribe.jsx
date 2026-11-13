import { BellOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLanguage, useT } from '../i18n/language.js'
import { villageName } from '../lib/village.js'
import { alertsAvailability, subscribe, unsubscribe } from '../services/alerts.js'
import { useAppState } from '../state/appState.js'

const KEY = 'safewindow.subscription'

function readSubscription() {
  try {
    return JSON.parse(localStorage.getItem(KEY))
  } catch {
    return null
  }
}

function writeSubscription(value) {
  try {
    if (value) localStorage.setItem(KEY, JSON.stringify(value))
    else localStorage.removeItem(KEY)
  } catch {
    // the button simply does not remember; the subscription itself is in Firestore
  }
}

/** "Alerts for this village": on, off, or why it is not possible here. */
export default function AlertSubscribe() {
  const t = useT()
  const { lang } = useLanguage()
  const { floodId, flood, village } = useAppState()
  const [availability, setAvailability] = useState('checking')
  const [sub, setSub] = useState(readSubscription)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState(null)
  const [detail, setDetail] = useState(null)       // the technical reason, small, for anyone helping

  useEffect(() => {
    alertsAvailability().then(setAvailability)
  }, [])

  if (!village) return <p className="muted small">{t('alerts_pick_village')}</p>
  if (availability === 'checking') return null
  if (availability !== 'ready') return <p className="muted small">{t(`alerts_${availability}`)}</p>

  const forThis = sub && sub.flood === floodId && sub.village === village.id
  const otherName = sub && !forThis ? flood.villages.find((v) => v.id === sub.village) : null

  async function turnOn() {
    setBusy(true)
    setProblem(null)
    try {
      await subscribe({ flood: floodId, village: village.id, lang })
      const value = { flood: floodId, village: village.id }
      writeSubscription(value)
      setSub(value)
    } catch (e) {
      setProblem(e.message === 'permission' ? 'alerts_denied' : 'alerts_failed')
      setDetail(e.code || e.message)
    }
    setBusy(false)
  }

  async function turnOff() {
    setBusy(true)
    setProblem(null)
    try {
      await unsubscribe()
      writeSubscription(null)
      setSub(null)
    } catch {
      setProblem('alerts_failed')
    }
    setBusy(false)
  }

  return (
    <div>
      {forThis ? (
        <>
          <p className="ok">{t('alerts_on', { name: villageName(village, lang) })}</p>
          <button className="btn secondary wide" onClick={turnOff} disabled={busy}>
            <BellOff size={18} aria-hidden="true" /> {t('alerts_turn_off')}
          </button>
        </>
      ) : (
        <>
          {sub && <p className="muted small">{t('alerts_other', { name: otherName ? villageName(otherName, lang) : sub.village })}</p>}
          <button className="btn wide" onClick={turnOn} disabled={busy}>
            {t('alerts_turn_on', { name: villageName(village, lang) })}
          </button>
        </>
      )}
      {problem && <p className="warn-text">{t(problem)}</p>}
      {problem && detail && <p className="muted small">({detail})</p>}
      <p className="muted small">{t('alerts_privacy')}</p>
    </div>
  )
}
