import { useState } from 'react'
import { useLanguage, useT } from '../i18n/language.js'

/** Status as words and a symbol, never colour alone. The texts never say more than the data shows. */
const SYMBOL = {
  PENDING: '●', TRIAGED: '◐', ASSIGNED: '◔', ACCEPTED: '✓', PREPARING: '…', DISPATCHED: '➜', IN_PROGRESS: '▶',
  RESCUED: '✔', ASSISTANCE_DELIVERED: '✔', CLOSED: '■', CANCELLED: '✕', DUPLICATE: '⧉', UNABLE_TO_REACH: '!', REFERRED: '↗', REJECTED: '✕',
}

export function StatusPill({ status }) {
  const t = useT()
  return <span className={`pill st-${status.toLowerCase()}`}><span aria-hidden="true">{SYMBOL[status] || '•'}</span> {t(`st_${status}`)}</span>
}

export function PriorityPill({ priority }) {
  const t = useT()
  return <span className={`pill pr-${String(priority).toLowerCase()}`}>{t(`pr_${priority}`)}</span>
}

/** A server time as a short local date and time. Shows a dash when the server has not stamped it yet. */
export function When({ value }) {
  const { lang } = useLanguage()
  const date = typeof value?.toDate === 'function' ? value.toDate() : value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return <span>—</span>
  return <time dateTime={date.toISOString()}>{date.toLocaleString(lang === 'bn' ? 'bn-BD' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</time>
}

/** A button that first asks for a reason, then runs `onConfirm(reason)`. Used where a reason is required. */
export function ReasonButton({ label, onConfirm, danger = false, minLength = 3, busy }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  if (!open) {
    return <button type="button" className={danger ? 'btn secondary danger-text' : 'btn secondary'} onClick={() => setOpen(true)}>{label}</button>
  }
  const ok = reason.trim().length >= minLength
  return (
    <div className="reason-box">
      <label className="field">
        <span>{t('rp_reason_label')}</span>
        <input type="text" value={reason} maxLength={280} onChange={(e) => setReason(e.target.value)} autoFocus />
      </label>
      <div className="row">
        <button type="button" className="btn" disabled={!ok || busy} onClick={async () => {
          await onConfirm(reason.trim())
          setOpen(false)
          setReason('')
        }}>{label}</button>
        <button type="button" className="btn secondary" onClick={() => setOpen(false)}>{t('rp_cancel_action')}</button>
      </div>
    </div>
  )
}

/** A group of tick boxes bound to an object of booleans. */
export function CheckGroup({ legend, keys, value, onChange, prefix }) {
  const t = useT()
  return (
    <fieldset className="checks">
      <legend>{legend}</legend>
      {keys.map((k) => (
        <label key={k} className="check">
          <input type="checkbox" checked={Boolean(value[k])} onChange={(e) => onChange({ ...value, [k]: e.target.checked })} />
          <span>{t(`${prefix}_${k}`)}</span>
        </label>
      ))}
    </fieldset>
  )
}

export function ErrorLine({ keyName }) {
  const t = useT()
  return keyName ? <p className="form-error" role="alert">{t(keyName)}</p> : null
}

/** The standing reminder on every rescue screen. Never claims a rescue is on its way. */
export function PrototypeNotice() {
  const t = useT()
  return <p className="notice" role="note"><span>{t('rp_prototype')}</span></p>
}
