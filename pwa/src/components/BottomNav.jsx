import { House, Map, MapPin, Settings, Siren } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useT } from '../i18n/language.js'

// Every button has an icon and a text label: never an icon alone.
const ITEMS = [
  { to: '/', key: 'nav_home', Icon: House },
  { to: '/map', key: 'nav_map', Icon: Map },
  { to: '/village', key: 'nav_village', Icon: MapPin },
  { to: '/emergency', key: 'nav_emergency', Icon: Siren },
  { to: '/settings', key: 'nav_settings', Icon: Settings },
]

export default function BottomNav() {
  const t = useT()
  return (
    <nav className="bottomnav" aria-label={t('nav_label')}>
      {ITEMS.map(({ to, key, Icon }) => (
        <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'navitem active' : 'navitem')}>
          <Icon size={22} strokeWidth={2} aria-hidden="true" />
          <span>{t(key)}</span>
        </NavLink>
      ))}
    </nav>
  )
}
