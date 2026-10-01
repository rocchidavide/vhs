/**
 * Internationalization. Source texts are English (locales/en.json); to add a language, add
 * locales/<code>.json, list it in SUPPORTED_LOCALES and in the backend LANGUAGES setting.
 * The language comes from the browser for now; a preference saved in the account will come
 * with the account section (post-MVP).
 */

import { createI18n } from 'vue-i18n'

import en from '@/locales/en.json'

export const SUPPORTED_LOCALES = ['en'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: AppLocale = 'en'

/** The first browser language VHS supports (matching on the base language), else English. */
export function detectLocale(languages: readonly string[] = navigator.languages): AppLocale {
  for (const language of languages) {
    const base = language.toLowerCase().split('-')[0]
    const match = SUPPORTED_LOCALES.find((locale) => locale === base)
    if (match) return match
  }
  return DEFAULT_LOCALE
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages: { en },
})

/** Translation outside components (API helpers, formatters). */
export const t = i18n.global.t
export const te = i18n.global.te

export function currentLocale(): string {
  return i18n.global.locale.value
}

/** Keep <html lang> in line with the interface language. */
export function applyDocumentLanguage(): void {
  document.documentElement.lang = currentLocale()
}
