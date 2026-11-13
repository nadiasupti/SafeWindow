import { Clock } from 'lucide-react'
import { useLanguage, useT } from '../i18n/language.js'
import { formatDate, formatDateTime } from '../lib/format.js'
import { useAppState } from '../state/appState.js'

/** Three different times, never merged: the radar image, publishing the results, and checking for new images. */
export default function TimesCard() {
  const t = useT()
  const { lang } = useLanguage()
  const { metadata } = useAppState().flood
  return (
    <div className="card">
      <h2><Clock size={20} aria-hidden="true" /> {t('times_title')}</h2>
      <dl className="facts">
        <dt>{t('radar_date')}</dt>
        <dd>{formatDate(metadata.observed_through, lang, true)}</dd>
        <dt>{t('published')}</dt>
        <dd>{formatDateTime(metadata.published_at, lang) || '–'}</dd>
        <dt>{t('last_checked')}</dt>
        <dd>{formatDateTime(metadata.last_checked, lang) || t('not_automated')}</dd>
      </dl>
    </div>
  )
}
