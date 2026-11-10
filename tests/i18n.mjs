// Verify the translation runtime: language detection, English fallback, placeholders, dates.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const transpile = (name) => ts.transpileModule(
  fs.readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS}}
).outputText;

const codes = {'locales/fr': transpile('locales/fr.ts'), 'i18n': transpile('i18n.ts')};

// Each language needs a fresh module instance because the language is cached.
const load = (locales, language) => {
  const cache = new Map();
  const globals = {
    window: locales ? {LocalizationManager: {m_rgLocalesToUse: locales}} : {},
    navigator: {language},
  };
  const require = (name) => {
    const key = name.replace(/^\.\//, '');
    if (!(key in codes)) throw new Error(`unexpected require: ${name}`);
    if (!cache.has(key)) {
      const output = {exports: {}};
      vm.runInNewContext(codes[key], {module: output, exports: output.exports, require, ...globals});
      cache.set(key, output.exports);
    }
    return cache.get(key);
  };
  return require('./i18n');
};

const steam = (locales) => load(locales, 'en-US');

const french = steam(['french', 'english']);
assert.equal(french.isFrench(), true, 'Steam locale name "french" selects French');
assert.equal(french.getLanguage(), 'fr');
assert.equal(french.getLocale(), 'fr-FR');
assert.equal(french.t('Done'), 'Terminé');

const regional = steam(['fr-CA']);
assert.equal(regional.getLanguage(), 'fr', 'regional French locales select French');
assert.equal(regional.t('Done'), 'Terminé');

const underscored = steam(['fr_CA']);
assert.equal(underscored.getLanguage(), 'fr', 'underscore separators are accepted');

const english = load(['english'], 'en-GB');
assert.equal(english.isFrench(), false);
assert.equal(english.getLanguage(), 'en');
assert.equal(english.getLocale(), 'en-US');
assert.equal(english.t('Done'), 'Done', 'English is the source language');

const german = load(['german'], 'de-DE');
assert.equal(german.t('Done'), 'Done', 'unsupported languages fall back to English');

const noSteam = load(undefined, 'en-US');
assert.equal(noSteam.t('Done'), 'Done', 'missing LocalizationManager does not throw');

assert.equal(french.t('Untranslated string'), 'Untranslated string', 'unknown keys fall back to English');
assert.equal(french.t('Hello {name}'), 'Hello {name}', 'unknown placeholders stay untouched');
assert.equal(
  french.t("Can't play {file}: {error}", {file: 'theme.m4a', error: 'codec'}),
  'Impossible de lire theme.m4a\u00A0: codec',
  'French placeholders are substituted'
);
assert.equal(
  english.t('{completed}/{total} completed • assigned {assigned}', {completed: 2, total: 5, assigned: 1}),
  '2/5 completed • assigned 1',
  'numbers are stringified'
);

const stamp = '2026-11-03T11:52:25-05:00';
assert.match(french.formatDateTime(stamp), /\bnov\./, 'French dates use French month names');
assert.match(english.formatDateTime(stamp), /\bNov\b/, 'English dates use English month names');
assert.notEqual(french.formatDateTime(stamp), stamp, 'valid timestamps are formatted');
assert.equal(english.formatDateTime('not a date'), 'not a date', 'invalid timestamps are returned unchanged');

console.log('Language detection, English fallback, placeholder, and localized date checks passed');
