import { useT } from '../i18n/language.js'
import { useAppState } from '../state/appState.js'

/** Wraps a screen: shows loading or an error until the chosen flood's data has arrived. */
export default function Loading({ children }) {
  const t = useT()
  const { ready, error } = useAppState()
  if (error && !ready) return <div className="card">{t('data_error')}</div>
  if (!ready) return <p className="muted">{t('loading')}</p>
  return children
}
