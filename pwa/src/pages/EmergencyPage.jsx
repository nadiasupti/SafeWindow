import { Backpack, ChevronDown, CircleCheck, HeartPulse, ListChecks, MessageSquare, Phone, PhoneCall, Siren } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Loading from '../components/Loading.jsx'
import Notice from '../components/Notice.jsx'
import PageHead from '../components/PageHead.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { formatNumber } from '../lib/format.js'
import { getPosition } from '../lib/gps.js'
import { compassArrow, nearest, villageName } from '../lib/village.js'
import { loadLayer } from '../services/data.js'
import { useAppState } from '../state/appState.js'

function Contacts() {
  const t = useT()
  const { lang } = useLanguage()
  const contacts = useAppState().flood.metadata.emergency_contacts || []
  const list = contacts.length ? contacts : [{ name: 'Emergency', number: '112' }]
  const [first, ...rest] = list
  return (
    <div className="card">
      <h2><Phone size={20} aria-hidden="true" /> {t('contacts_title')}</h2>
      <a className="call-main" href={`tel:${first.number}`}>
        <span className="call-icon" aria-hidden="true"><PhoneCall size={26} /></span>
        <span>
          <span className="call-name">{first[`name_${lang}`] || first.name}</span>
          <span className="call-number">{first.number}</span>
        </span>
        <span className="call-go">{t('call_now')}</span>
      </a>
      {rest.length > 0 && (
        <ul className="plain">
          {rest.map((c) => (
            <li key={c.number}>
              <a className="btn call" href={`tel:${c.number}`}>
                <Phone size={18} aria-hidden="true" /> {c[`name_${lang}`] || c.name}: <strong>{c.number}</strong>
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">{t('contacts_check')}</p>
    </div>
  )
}

function Health() {
  const t = useT()
  const { lang } = useLanguage()
  const { floodId, village } = useAppState()
  const [places, setPlaces] = useState(null)
  useEffect(() => {
    loadLayer(floodId, 'health').then((g) => setPlaces(
      (g?.features || []).map((f) => ({ name: f.properties.name, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] }))))
  }, [floodId])
  let line = t('health_pick')
  if (village && places) {
    const hit = nearest(places, village.lat, village.lon)
    line = hit
      ? t('health_line', { name: hit.item.name, km: formatNumber(hit.km, lang, 1),
        dir: compassArrow(village.lat, village.lon, hit.item.lat, hit.item.lon) })
      : t('health_none')        // never silent: say what to do when nothing is listed
  }
  return (
    <div className="card">
      <h2><HeartPulse size={20} aria-hidden="true" /> {t('health_title')}</h2>
      <p>{line}</p>
    </div>
  )
}

function HelpSms() {
  const t = useT()
  const { lang } = useLanguage()
  const { village } = useAppState()
  const [people, setPeople] = useState(5)

  async function write() {
    let loc = t('no_loc')
    try {
      const p = await getPosition()
      loc = `${p.lat.toFixed(5)},${p.lon.toFixed(5)}`
    } catch {
      // no GPS: the message says the location is unknown
    }
    const body = t('help_body', { name: village ? villageName(village, lang) : '-', p: people, loc })
    window.location.href = `sms:?&body=${encodeURIComponent(body)}`
  }

  return (
    <div className="card">
      <h2><MessageSquare size={20} aria-hidden="true" /> {t('help_title')}</h2>
      <label className="field">
        <span className="field-label">{t('help_people')}</span>
        <input type="number" min="1" max="999" value={people}
          onChange={(e) => setPeople(Math.max(1, Number(e.target.value) || 1))} />
      </label>
      <button className="btn wide" onClick={write}>
        <MessageSquare size={18} aria-hidden="true" /> {t('help_btn')}
      </button>
      <p className="muted small">{t('help_note')}</p>
    </div>
  )
}

export default function EmergencyPage() {
  const t = useT()
  const { lang } = useLanguage()
  const { supplyDays } = useAppState()
  return (
    <section>
      <PageHead Icon={Siren} tone="red" title={t('emergency_title')} sub={t('page_emergency_sub')} />
      <Loading>
        <Contacts />
        <Link className="btn wide" to="/rescue"><Siren size={18} aria-hidden="true" /> {t('rp_emergency_link')}</Link>
        <p className="muted small">{t('rp_emergency_link_note')}</p>
        <HelpSms />
        <Health />
        <div className="card">
          <h2><Backpack size={20} aria-hidden="true" /> {t('bag_title')}</h2>
          <ul className="checklist">
            {t('bag_items', { n: formatNumber(supplyDays, lang) }).map((item) => (
              <li key={item}><CircleCheck size={18} aria-hidden="true" /><span>{item}</span></li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h2><ListChecks size={20} aria-hidden="true" /> {t('stages_title')}</h2>
          {['before', 'during', 'after'].map((stage) => (
            <details key={stage} className="stage" open={stage === 'before'}>
              <summary>{t(`stage_${stage}_title`)}<ChevronDown className="chev" size={20} aria-hidden="true" /></summary>
              <ul>{t(`stage_${stage}`).map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          ))}
        </div>
        <Notice />
      </Loading>
    </section>
  )
}
