// Exercise the production storage component's confirmation and API contracts.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const transpile = (name) => ts.transpileModule(fs.readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, jsxFactory: 'window.SP_REACT.createElement', jsxFragmentFactory: 'window.SP_REACT.Fragment'}}).outputText;
const errors = {exports: {}};
vm.runInNewContext(transpile('error-message.ts'), {exports: errors.exports, module: errors});
function harness(componentName, overrides = {}) {
  let slots = [], cursor = 0, effects = [], changed = true, tree;
  const calls = [];
  const file = {id: 'downloads/1/shared.m4a', name: 'shared.m4a', path: '/settings/downloads/1/shared.m4a', category: 'downloads', bytes: 4096, assignments: ['1', '__global__']};
  const storage = {files: [file], total_bytes: 4096, download_bytes: 4096, preview_bytes: 0, unused_bytes: 0, missing_assignments: ['9'], busy: false};
  const React = {
    Fragment: 'Fragment',
    createElement: (type, props, ...children) => ({type, props: props || {}, children: children.flat(Infinity)}),
    useState(initial) { const key = cursor++; if (!(key in slots)) slots[key] = initial; return [slots[key], value => {slots[key] = typeof value === 'function' ? value(slots[key]) : value; changed = true;}]; },
    useRef(initial) {const key = cursor++; return slots[key] ||= {current: initial};},
    useEffect(fn, deps) {const key = cursor++; const previous = slots[key]; if (!previous || deps.some((value, index) => !Object.is(value, previous[index]))) {slots[key] = deps; effects.push(fn);}},
  };
  const apis = {
    get_song_storage: async () => storage,
    delete_song_storage: async (...args) => {calls.push(['delete', ...args]); return {freed_bytes: 4096, storage: {...storage, files: [], total_bytes: 0}};},
    clean_song_storage: async category => {calls.push(['clean', category]); return {freed_bytes: 0, storage};},
    clear_missing_song_assignments: async () => {calls.push(['missing']); return {...storage, missing_assignments: []};},
    ...overrides,
  };
  const output = {exports: {}};
  const sandbox = {exports: output.exports, module: output, window: {SP_REACT: React, setTimeout: fn => fn()}, require: name => name === 'react' ? React : name === '@decky/api' ? {callable: name => apis[name]} : name === './error-message' ? errors.exports : {Navigation: {NavigateBack() {}}, PanelSection: 'section', PanelSectionRow: 'row', ScrollPanel: 'scroll', Spinner: 'spinner'}};
  vm.runInNewContext(transpile('song-storage.tsx'), sandbox);
  const props = {Button: 'button', onChanged: () => calls.push(['changed']), assignment: '1', path: file.path, onDeleted: () => calls.push(['changed'])};
  const render = () => {cursor = 0; effects = []; changed = false; tree = output.exports[componentName](props); effects.forEach(fn => fn());};
  const settle = async () => {for (let i = 0; i < 8; i++) {if (changed || !tree) render(); await Promise.resolve();} return tree;};
  const text = node => node == null || typeof node === 'boolean' ? '' : typeof node !== 'object' ? String(node) : (node.children || []).map(text).join(' ');
  const find = (node, label) => {
    if (!node || typeof node !== 'object') return null;
    if (node.type === 'button' && text(node).trim().replace(/\(\s+/g, '(').replace(/\s+\)/g, ')') === label) return node;
    for (const child of node.children || []) {const found = find(child, label); if (found) return found;}
    return null;
  };
  const click = async label => {await settle(); const button = find(tree, label); assert.ok(button, `Missing button: ${label}`); assert.ok(!button.props.disabled, `Disabled button: ${label}`); const promise = button.props.onClick(); if (promise?.then) await promise; await settle();};
  return {calls, storage, file, settle, click, text: () => text(tree), get tree() {return tree;}};
}
const screen = harness('SongStorage');
await screen.settle();
assert.match(screen.text(), /4.0 KiB/);
await screen.click('Delete from disk…');
assert.equal(screen.calls.length, 0, 'Opening confirmation must not delete');
assert.match(screen.text(), /Global ambient/);
await screen.click('Cancel');
assert.equal(screen.calls.length, 0);
await screen.click('Delete from disk…');
await screen.click('Confirm permanent deletion');
assert.equal(screen.calls[0][0], 'delete');
assert.equal(screen.calls[0][1], screen.file.id);
assert.equal(screen.calls[0][2], true);
assert.equal(Array.from(screen.calls[0][3]).join(','), '1,__global__');
assert.match(screen.text(), /Freed 4.0 KiB/);
assert.equal(screen.calls[1][0], 'changed');
const missing = harness('SongStorage');
await missing.settle();
await missing.click('Clear missing-file assignments (1)');
await missing.click('Confirm clear assignments');
assert.equal(missing.calls[0][0], 'missing');
assert.ok(!missing.calls.some(call => call[0] === 'delete'));
const failure = harness('SongStorage', {delete_song_storage: async () => {throw {python_message: 'File is read only'};}});
await failure.settle();
await failure.click('Delete from disk…');
await failure.click('Confirm permanent deletion');
assert.match(failure.text(), /File is read only/);
assert.ok(!failure.calls.length, 'Failed deletion must not notify an assignment change');
const caches = harness('SongStorage');
caches.storage.files[0].assignments = [];
caches.storage.files[0].category = 'previews';
await caches.settle();
await caches.click('Clear cached previews');
assert.equal(caches.calls.length, 0, 'Bulk cleanup also requires confirmation');
await caches.click('Confirm permanent deletion');
assert.equal(caches.calls[0].join(','), 'clean,previews');
const unused = harness('SongStorage');
unused.storage.files[0].assignments = [];
await unused.settle();
await unused.click('Delete all unused files');
await unused.click('Confirm permanent deletion');
assert.equal(unused.calls[0].join(','), 'clean,unused');
const direct = harness('DeleteAssignedSong');
await direct.settle();
await direct.click('Delete downloaded file from disk…');
assert.equal(direct.calls.length, 0);
await direct.click('Confirm permanent deletion');
assert.equal(direct.calls[0][0], 'delete');
const local = harness('DeleteAssignedSong', {get_song_storage: async () => ({files: []})});
await local.settle();
assert.equal(local.tree, null, 'Do not offer deletion for external local music');
console.log('Storage UI confirmation, shared references, disk-space feedback, missing-reference repair, error display, and local-file protection checks passed');
