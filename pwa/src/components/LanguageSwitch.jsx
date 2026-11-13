import { Languages } from 'lucide-react'
import { LANGUAGES, useLanguage, useT } from '../i18n/language.js'

/** One tap in the top bar switches Bangla <-> English; the button names the language it switches to. */
export default function LanguageSwitch() {
  const t = useT()
  const { lang, setLang } = useLanguage()
  const next = LANGUAGES.find((l) => l.code !== lang) || LANGUAGES[0]
  return (
    <button className="lang-switch" onClick={() => setLang(next.code)} aria-label={`${t('lang_switch')}: ${next.name}`}
      lang={next.code}>
      <Languages size={18} aria-hidden="true" />
      {next.name}
    </button>
  )
}
