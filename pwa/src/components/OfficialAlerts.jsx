import { Megaphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useT } from '../i18n/language.js'
import { useAppState } from '../state/appState.js'
import { When } from './RescueBits.jsx'

/**
 * Official alerts written by government (publicly readable). Shown only when they are current, never invented here.
 * The rescue code is loaded only when this runs, so the village app's first screen stays light and works offline.
 */
export default function OfficialAlerts() {
  const t = useT()
  const { floodId } = useAppState()
  const [items, setItems] = useState([])
  useEffect(() => {
    let alive = true
    import('../services/rescue.js')
      .then((m) => m.officialAlerts(20))
      .then((list) => {
        const now = Date.now()
        const current = list.filter((a) => a.status === 'published' && a.flood === floodId
          && a.starts_at?.toMillis() <= now && a.expires_at?.toMillis() > now)
        if (alive) setItems(current)
      })
      .catch(() => alive && setItems([]))        // offline or no permission: show nothing
    return () => { alive = false }
  }, [floodId])
  if (!items.length) return null
  return (
    <div className="card official" role="region" aria-label={t('rp_official_title')}>
      <h2><Megaphone size={20} aria-hidden="true" /> {t('rp_official_title')}</h2>
      {items.map((a) => (
        <div key={a.id}>
          <p><strong>{t(`rp_sev_${a.severity}`)} · {a.title}</strong></p>
          <p>{a.body}</p>
          <p className="muted small">{t('rp_alert_source')}: {a.source} · <When value={a.starts_at} /> → <When value={a.expires_at} /></p>
        </div>
      ))}
    </div>
  )
}
