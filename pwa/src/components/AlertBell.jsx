import { Bell } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage, useT } from '../i18n/language.js'
import { ALERT_EVENT, lastSeen, listAlerts } from '../lib/alertStore.js'
import { formatNumber } from '../lib/format.js'

/** The bell in the top bar: opens the alerts page and shows how many alerts arrived since it was last opened. */
export default function AlertBell() {
  const t = useT()
  const { lang } = useLanguage()
  const [unseen, setUnseen] = useState(0)

  useEffect(() => {
    let alive = true
    const count = () => listAlerts()
      .then((list) => alive && setUnseen(list.filter((a) => (a.sent_at || '') > lastSeen()).length))
      .catch(() => {})
    count()
    window.addEventListener(ALERT_EVENT, count)
    return () => {
      alive = false
      window.removeEventListener(ALERT_EVENT, count)
    }
  }, [])

  const label = unseen ? t('alerts_new', { n: formatNumber(unseen, lang) }) : t('alerts_page')
  return (
    <Link to="/alerts" className="bell" aria-label={label} title={label}>
      <Bell size={22} aria-hidden="true" />
      {unseen > 0 && <span className="bell-count" aria-hidden="true">{formatNumber(Math.min(unseen, 99), lang)}</span>}
    </Link>
  )
}
