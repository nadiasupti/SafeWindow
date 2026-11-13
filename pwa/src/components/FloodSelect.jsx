import { useT } from '../i18n/language.js'
import { useAppState } from '../state/appState.js'

export default function FloodSelect() {
  const t = useT()
  const { floods, floodId, setFloodId } = useAppState()
  if (!floods || floods.length < 2) return null
  return (
    <label className="field">
      <span className="field-label">{t('flood')}</span>
      <select value={floodId || ''} onChange={(e) => setFloodId(e.target.value)}>
        {floods.map((f) => (
          <option key={f.id} value={f.id}>{f.name}</option>
        ))}
      </select>
    </label>
  )
}
