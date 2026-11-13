// Fonts are bundled with the app (no Google Fonts, no CDN), so Bangla text still renders offline.
import '@fontsource/noto-sans-bengali/400.css'
import '@fontsource/noto-sans-bengali/600.css'
import '@fontsource/noto-sans-bengali/700.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import './styles/app.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import App from './App.jsx'
import LanguageProvider from './i18n/LanguageProvider.jsx'
import AppStateProvider from './state/AppStateProvider.jsx'

// When a new version is deployed, it takes over and the page reloads once on its own,
// so an installed app never stays on an old version until it is closed by hand.
registerSW({ immediate: true })

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LanguageProvider>
      <AppStateProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AppStateProvider>
    </LanguageProvider>
  </StrictMode>,
)
