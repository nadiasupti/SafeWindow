import { createContext, useContext } from 'react'
import bn from '../locales/bn.json'
import en from '../locales/en.json'

export const TEXTS = { bn, en }
export const LANGUAGES = [
  { code: 'bn', name: 'বাংলা' },
  { code: 'en', name: 'English' },
]
export const STORAGE_KEY = 'safewindow.lang'

export const LanguageContext = createContext({ lang: 'bn', setLang: () => {} })

export function savedLanguage() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value in TEXTS ? value : 'bn'
  } catch {
    return 'bn'     // private mode or blocked storage: Bangla first
  }
}

export function useLanguage() {
  return useContext(LanguageContext)
}

function fill(text, vars) {
  return text.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? String(vars[name]) : `{${name}}`))
}

/**
 * t('key', {n: 3}) -> text in the chosen language, falling back to English, then to the key.
 * A key holding a list (e.g. bag_items) gives a list of texts.
 */
export function useT() {
  const { lang } = useLanguage()
  return (key, vars = {}) => {
    const value = TEXTS[lang][key] ?? TEXTS.en[key] ?? key
    return Array.isArray(value) ? value.map((item) => fill(item, vars)) : fill(value, vars)
  }
}
