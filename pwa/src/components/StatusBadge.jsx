import { useT } from '../i18n/language.js'
import { STATUS } from '../lib/village.js'

/** A status as colour + symbol + word, so it reads without colour too. */
export default function StatusBadge({ code, large = false }) {
  const t = useT()
  const s = STATUS[code] || STATUS.u
  return (
    <span className={large ? 'badge large' : 'badge'} style={{ '--c': s.color }}>
      <span className="badge-symbol" aria-hidden="true">{s.symbol}</span>
      {t(s.key)}
    </span>
  )
}
