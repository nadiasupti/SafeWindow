import { LocateFixed, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useLanguage, useT } from '../i18n/language.js'
import { formatNumber } from '../lib/format.js'
import { getPosition } from '../lib/gps.js'
import { nearest, statusCode, villageName } from '../lib/village.js'
import { useAppState } from '../state/appState.js'
import StatusBadge from './StatusBadge.jsx'

const FAR_KM = 30      // farther than this from every village: probably outside the flood area

/** Choose a village from a searchable list (most urgent first), or the nearest one by GPS. */
export default function VillagePicker({ onPicked }) {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, dateIndex, setVillageId } = useAppState()
  const [query, setQuery] = useState('')
  const [gps, setGps] = useState(null)

  const villages = useMemo(() => {
    const q = query.trim().toLowerCase()
    return [...flood.villages]
      .filter((v) => !q || v.name.toLowerCase().includes(q) || (v.name_local || '').includes(query.trim()))
      .sort((a, b) => (a.urgency_rank ?? 999) - (b.urgency_rank ?? 999) || villageName(a, lang).localeCompare(villageName(b, lang)))
  }, [flood, query, lang])

  function pick(id) {
    setVillageId(id)
    onPicked?.()
  }

  async function findByGps() {
    setGps({ state: 'finding' })
    try {
      const pos = await getPosition()
      const hit = nearest(flood.villages, pos.lat, pos.lon)
      setGps({ state: 'found', village: hit.item, km: hit.km })
    } catch {
      setGps({ state: 'failed' })
    }
  }

  return (
    <div className="picker">
      <button className="btn secondary wide" onClick={findByGps}>
        <LocateFixed size={18} aria-hidden="true" /> {t('find_by_gps')}
      </button>
      {gps?.state === 'finding' && <p className="muted">{t('gps_finding')}</p>}
      {gps?.state === 'failed' && <p className="muted">{t('gps_failed')}</p>}
      {gps?.state === 'found' && (
        <div className="card soft">
          <p>{t(gps.km > FAR_KM ? 'gps_far' : 'gps_nearest', {
            name: villageName(gps.village, lang), km: formatNumber(gps.km, lang, 1) })}</p>
          {gps.km <= FAR_KM && <button className="btn" onClick={() => pick(gps.village.id)}>{t('use_this')}</button>}
        </div>
      )}
      <p className="muted small">{t('gps_private')}</p>

      <label className="search">
        <Search size={18} aria-hidden="true" />
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('search_village')} />
      </label>
      <ul className="village-list">
        {villages.map((v) => (
          <li key={v.id}>
            <button onClick={() => pick(v.id)}>
              <span className="vname">{villageName(v, lang)}</span>
              <StatusBadge code={statusCode(flood, v.id, dateIndex)} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
