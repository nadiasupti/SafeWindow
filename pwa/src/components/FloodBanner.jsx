import { TriangleAlert } from 'lucide-react'
import { useT } from '../i18n/language.js'
import { useAppState } from '../state/appState.js'

/** Shown for demonstration floods, whose results are not validated. */
export default function FloodBanner() {
  const t = useT()
  const { flood } = useAppState()
  if (!flood?.metadata.demonstration) return null
  return (
    <div className="banner" role="note">
      <TriangleAlert size={18} aria-hidden="true" /> {t('demo_banner')}
    </div>
  )
}
