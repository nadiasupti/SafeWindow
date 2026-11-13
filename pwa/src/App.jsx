import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes, Link } from 'react-router-dom'
import AlertBell from './components/AlertBell.jsx'
import ProfileButton from './components/ProfileButton.jsx'
import AlertListener from './components/AlertListener.jsx'
import BottomNav from './components/BottomNav.jsx'
import LanguageSwitch from './components/LanguageSwitch.jsx'
import { useT } from './i18n/language.js'
import AlertsPage from './pages/AlertsPage.jsx'
import AnalysisPage from './pages/AnalysisPage.jsx'
import EmergencyPage from './pages/EmergencyPage.jsx'
import HomePage from './pages/HomePage.jsx'
import MapPage from './pages/MapPage.jsx'
import NisarPage from './pages/NisarPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import VillagePage from './pages/VillagePage.jsx'

// The rescue platform (accounts, NGO, government) loads only when opened: the village app stays light and offline-first.
const AccountPage = lazy(() => import('./pages/AccountPage.jsx'))
const RescuePage = lazy(() => import('./pages/RescuePage.jsx'))
const NgoPage = lazy(() => import('./pages/NgoPage.jsx'))
const GovPage = lazy(() => import('./pages/GovPage.jsx'))

export default function App() {
  const t = useT()
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand-link" aria-label={t('go_home')}>
          <img className="brand" src="/brand/logo-header.png" alt={t('app_name')} width="163" height="40" />
        </Link>
        <span className="topbar-right">
          <LanguageSwitch />
          <AlertBell />
          <ProfileButton />
        </span>
      </header>
      <main className="screen">
        <Suspense fallback={<p className="muted">{t('loading')}</p>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/village" element={<VillagePage />} />
          <Route path="/emergency" element={<EmergencyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/nisar" element={<NisarPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/rescue" element={<RescuePage />} />
          <Route path="/ngo" element={<NgoPage />} />
          <Route path="/gov" element={<GovPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </main>
      <BottomNav />
      <AlertListener />
    </div>
  )
}
