import { fr } from "./locales/fr";

export type TranslationVars = Record<string, string | number>;

const FRENCH_LOCALES = new Set([
  "fr",
  "fr-fr",
  "fr-be",
  "fr-ca",
  "fr-ch",
  "french",
]);

let cachedLanguage: "en" | "fr" | null = null;

const readSteamLocale = (): string => {
  try {
    const locales = window.LocalizationManager?.m_rgLocalesToUse;
    if (Array.isArray(locales)) {
      const locale = locales.find(
        (entry) => typeof entry === "string" && entry.trim().length > 0,
      );
      if (locale) return locale;
    }
  } catch (_ignored) {
    // Not running inside the Steam client (for example, in tests).
  }
  try {
    return navigator.language || "";
  } catch (_ignored) {
    return "";
  }
};

/** Steam UI language of the current session, limited to the languages we ship. */
export const getLanguage = (): "en" | "fr" => {
  if (cachedLanguage) return cachedLanguage;
  const locale = readSteamLocale().trim().toLowerCase();
  cachedLanguage = FRENCH_LOCALES.has(locale) || locale.startsWith("fr-")
    ? "fr"
    : "en";
  return cachedLanguage;
};

/** True when the Steam UI is running in French. */
export const isFrench = (): boolean => getLanguage() === "fr";

/**
 * Translate an English UI string.
 *
 * English is the source language: the English text itself is the key, so an
 * untranslated (or newly added) string always falls back to English. Vars are
 * substituted into `{name}` placeholders.
 */
export const t = (english: string, vars?: TranslationVars): string => {
  let text = getLanguage() === "fr" ? fr[english] ?? english : english;
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, (match, name: string) =>
      name in vars ? String(vars[name]) : match,
    );
  }
  return text;
};
