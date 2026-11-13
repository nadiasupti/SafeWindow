import { useEffect, useMemo, useState } from 'react'
import { LanguageContext, STORAGE_KEY, savedLanguage } from './language.js'

export default function LanguageProvider({ children }) {
  const [lang, setLang] = useState(savedLanguage)
  useEffect(() => {
    document.documentElement.lang = lang
    try {
      localStorage.setItem(STORAGE_KEY, lang)
    } catch {
      // the choice simply is not remembered
    }
  }, [lang])
  const value = useMemo(() => ({ lang, setLang }), [lang])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}
