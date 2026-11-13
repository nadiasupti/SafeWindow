import { Pause, Play, SkipBack, SkipForward } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLanguage, useT } from '../i18n/language.js'
import { coverage } from '../lib/coverage.js'
import { formatDate, formatNumber } from '../lib/format.js'
import { useAppState } from '../state/appState.js'

const STEP_MS = 1800     // time on each radar date while playing

/**
 * Step through the radar dates, by hand or as a replay. Only the pipeline's own radar dates are offered; a date
 * the radar did not see is shown as such (grey map, unknown villages), never filled from an earlier image.
 * Everything else (flood image, flooded roads, village status) follows the same dateIndex.
 */
export default function DateSlider() {
  const t = useT()
  const { lang } = useLanguage()
  const { flood, dateIndex, setDateIndex } = useAppState()
  const [playing, setPlaying] = useState(false)
  const dates = flood.status.dates
  const last = dates.length - 1
  const date = dates[dateIndex]
  const cov = coverage(flood, dateIndex)

  // while playing: one step forward every STEP_MS, and stop on the last date
  useEffect(() => {
    if (!playing) return undefined
    if (dateIndex >= last) {
      const stop = setTimeout(() => setPlaying(false), 0)
      return () => clearTimeout(stop)
    }
    const timer = setTimeout(() => setDateIndex(dateIndex + 1), STEP_MS)
    return () => clearTimeout(timer)
  }, [playing, dateIndex, last, setDateIndex])

  function togglePlay() {
    if (playing) setPlaying(false)
    else {
      if (dateIndex >= last) setDateIndex(0)      // at the end, play starts again from the first date
      setPlaying(true)
    }
  }

  function goTo(i) {
    setPlaying(false)
    setDateIndex(Math.min(last, Math.max(0, i)))
  }

  return (
    <div className="dateslider">
      <div className="ds-head">
        <label className="field-label" htmlFor="date-range">
          {t('date')}: <strong className="ds-date">{formatDate(date, lang, true)}</strong>
        </label>
        <span className="ds-pos">{t('replay_pos', { i: formatNumber(dateIndex + 1, lang), n: formatNumber(dates.length, lang) })}</span>
      </div>
      <div className="ds-controls noprint">
        <button className="ds-btn" onClick={() => goTo(dateIndex - 1)} disabled={dateIndex === 0}
          aria-label={t('replay_prev')} title={t('replay_prev')}>
          <SkipBack size={20} aria-hidden="true" />
        </button>
        <button className={playing ? 'ds-btn ds-play on' : 'ds-btn ds-play'} onClick={togglePlay} aria-pressed={playing}>
          {playing ? <Pause size={20} aria-hidden="true" /> : <Play size={20} aria-hidden="true" />}
          {playing ? t('replay_pause') : t('replay_play')}
        </button>
        <button className="ds-btn" onClick={() => goTo(dateIndex + 1)} disabled={dateIndex === last}
          aria-label={t('replay_next')} title={t('replay_next')}>
          <SkipForward size={20} aria-hidden="true" />
        </button>
      </div>
      <input id="date-range" type="range" min={0} max={last} value={dateIndex}
        onChange={(e) => goTo(Number(e.target.value))} aria-valuetext={formatDate(date, lang, true)} />
      {/* one mark per radar date: how much the radar saw (also readable as text below, not by colour alone) */}
      <div className="ds-ticks" aria-hidden="true">
        {dates.map((d, i) => (
          <span key={d} className={`ds-tick ${coverage(flood, i).kind}${i === dateIndex ? ' active' : ''}`} />
        ))}
      </div>
      <p className={`ds-cov ${cov.kind}`} role="status">
        {cov.kind === 'none' && t('cov_none')}
        {cov.kind === 'partial' && t('no_radar_note', { p: formatNumber(cov.unknown, lang) })}
        {cov.kind === 'full' && t('cov_full')}
      </p>
    </div>
  )
}
