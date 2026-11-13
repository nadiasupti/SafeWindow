import { Download } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useLanguage, useT } from '../i18n/language.js'
import { formatDate, formatNumber } from '../lib/format.js'
import { downloadFlood, downloadSize, isReady, offlineSupported } from '../services/offline.js'
import { useAppState } from '../state/appState.js'

/** "Download this area's map", and whether the chosen flood is ready to use offline. */
export default function OfflineCard() {
  const t = useT()
  const { lang } = useLanguage()
  const { floodId, flood } = useAppState()
  const [state, setState] = useState(() => ({ kind: offlineSupported() ? 'checking' : 'unsupported' }))
  const [mb, setMb] = useState(null)

  const readiness = useCallback(async () => ({ kind: (await isReady(floodId)) ? 'ready' : 'not' }), [floodId])

  useEffect(() => {
    if (!offlineSupported()) return undefined
    let alive = true
    readiness().then((s) => alive && setState(s))
    downloadSize(floodId).then((v) => alive && setMb(v))
    return () => {
      alive = false
    }
  }, [readiness, floodId])

  async function download() {
    setState({ kind: 'progress', p: 0 })
    try {
      await downloadFlood(floodId, (p) => setState({ kind: 'progress', p }))
      setState(await readiness())
    } catch {
      setState({ kind: 'failed' })
    }
  }

  return (
    <div className="card">
      <h2><Download size={20} aria-hidden="true" /> {t('offline_title')}</h2>
      {state.kind === 'ready' && (
        <p className="ok">{t('offline_ready', { d: formatDate(flood.metadata.observed_through, lang, true) })}</p>
      )}
      {(state.kind === 'not' || state.kind === 'failed') && <p>{t('offline_not')}</p>}
      {state.kind === 'failed' && <p className="warn-text">{t('offline_failed')}</p>}
      {state.kind === 'unsupported' && <p>{t('offline_unsupported')}</p>}
      {state.kind === 'progress' && (
        <>
          <p>{t('offline_progress', { p: formatNumber(state.p, lang) })}</p>
          <progress max="100" value={state.p} />
        </>
      )}
      {(state.kind === 'not' || state.kind === 'failed' || state.kind === 'ready') && (
        <button className={state.kind === 'ready' ? 'btn secondary wide' : 'btn wide'} onClick={download}>
          <Download size={18} aria-hidden="true" />
          {t('offline_download', { mb: mb == null ? '…' : formatNumber(mb, lang, 1) })}
        </button>
      )}
      <p className="muted small">{t('offline_help')}</p>
    </div>
  )
}
