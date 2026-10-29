/* Interface language (English / French).
 *
 * Every visible text goes through t('some.key'). The texts themselves live
 * in en.js and fr.js — one flat object per language, same keys in both.
 * To add a language: copy en.js to xx.js, translate the values, and add it
 * to DICTIONARIES and LANGUAGES below. Nothing else changes.
 *
 *   const { t, lang, formatNumber, formatDateTime } = useI18n()
 *   t('cases.title')                          -> "Analysis cases"
 *   t('cases.count', { count: 3 })            -> "3 cases"  (plural, see below)
 *   t('cases.deleted', { client: 'ACME' })    -> 'Case "ACME" was deleted.'
 *
 * Plurals: when a {count} is given, the key "x.one" is used for 1 (and for
 * 0 in French) and "x.other" otherwise; a plain "x" is used if neither exists.
 *
 * The chosen language is remembered in this browser (localStorage) and sent
 * to the backend with every request (Accept-Language, in api/client.js), so
 * the AI commentary is written in the same language as the screen.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '../api/client.js'
import en from './en.js'
import fr from './fr.js'

const DICTIONARIES = { en, fr }

export const LANGUAGES = [
  { code: 'en', label: 'English', locale: 'en-GB' },
  { code: 'fr', label: 'Français', locale: 'fr-FR' },
]

const STORAGE_KEY = 'ui-language'

function initialLanguage() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved && DICTIONARIES[saved]) return saved
  } catch {
    // private window / blocked storage: fall through to the browser's language
  }
  const browser = (navigator.language || 'en').slice(0, 2).toLowerCase()
  return DICTIONARIES[browser] ? browser : 'en'
}

function pick(dictionary, key, vars) {
  if (vars && typeof vars.count === 'number') {
    const one = dictionary.__pluralOne ? dictionary.__pluralOne(vars.count) : vars.count === 1
    const plural = dictionary[`${key}.${one ? 'one' : 'other'}`]
    if (plural !== undefined) return plural
  }
  return dictionary[key]
}

export function translate(lang, key, vars) {
  const text = pick(DICTIONARIES[lang] || en, key, vars) ?? pick(en, key, vars) ?? key
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (match, name) =>
    vars[name] === undefined || vars[name] === null ? match : String(vars[name])
  )
}

const I18nContext = createContext(null)

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(initialLanguage)

  // Set before the first request goes out, and on every change.
  api.setLanguage(lang)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = useCallback((next) => {
    if (!DICTIONARIES[next]) return
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // not remembered, but still switched for this visit
    }
    api.setLanguage(next)
    setLangState(next)
  }, [])

  const value = useMemo(() => {
    const locale = LANGUAGES.find((item) => item.code === lang)?.locale || 'en-GB'
    return {
      lang,
      locale,
      setLang,
      t: (key, vars) => translate(lang, key, vars),
      // Amounts: 1 234 567 in French, 1,234,567 in English.
      formatNumber: (value, options) =>
        value === null || value === undefined || value === '' || Number.isNaN(Number(value))
          ? String(value ?? '')
          : Number(value).toLocaleString(locale, options),
      formatDateTime: (value) => (value ? asDate(value).toLocaleString(locale) : ''),
      formatDate: (value) => (value ? asDate(value).toLocaleDateString(locale) : ''),
    }
  }, [lang, setLang])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

/* Every time the backend stores is UTC. A time read back from the database
 * comes without its time zone ("2026-10-27T10:05:02"), and a browser reads
 * such a string as LOCAL time — in Douala (UTC+1) every time would show one
 * hour early. So a date-time without a zone is read as UTC; the browser then
 * shows it in the user's own time zone. */
const NO_ZONE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/
export function asDate(value) {
  return new Date(typeof value === 'string' && NO_ZONE.test(value) ? `${value}Z` : value)
}

export function useI18n() {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n() must be used inside <LanguageProvider>')
  return value
}

/* The language picker shown in the header (and on the sign-in page). */
export function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n()
  return (
    <select
      aria-label={t('language.label')}
      title={t('language.label')}
      value={lang}
      onChange={(event) => setLang(event.target.value)}
      style={{ width: 'auto' }}
    >
      {LANGUAGES.map((item) => (
        <option key={item.code} value={item.code}>
          {item.label}
        </option>
      ))}
    </select>
  )
}

/* A name the backend sends in English, translated by its code when the
 * dictionary has it: labelByCode(t, 'ratio', 'R1', 'Current ratio').
 * Falls back to the backend's text for anything not in the dictionary. */
export function labelByCode(t, prefix, code, fallback) {
  const key = `${prefix}.${code}`
  const text = t(key)
  return text === key ? fallback ?? code : text
}