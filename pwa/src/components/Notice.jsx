import { Info } from 'lucide-react'
import { useT } from '../i18n/language.js'
import { useAppState } from '../state/appState.js'

/** The standing reminder: research tool, follow official alerts. */
export default function Notice() {
  const t = useT()
  const agencies = useAppState().flood?.metadata.agencies?.join(', ') || '—'
  return (
    <p className="notice">
      <Info size={18} aria-hidden="true" />
      <span>{t('official_notice', { agencies })}</span>
    </p>
  )
}
