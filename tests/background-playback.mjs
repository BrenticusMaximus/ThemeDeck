// Exercise the production policy, running-app transitions, and track resolver.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../src/index.tsx', import.meta.url), 'utf8');
const tree = ts.createSourceFile('index.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = new Set(['readPreference', 'readBackgroundMusicSetting', 'readMainMenuContext', 'isBackgroundMenuPlaybackAllowed', 'shouldBlockRunningPlayback', 'setRunningGameAppId', 'refreshMainMenuContext', 'handleBackgroundMusicChanged', 'resolveAutoTrackFromContext']);
const functions = tree.statements.filter(node => ts.isVariableStatement(node) && names.has(node.declarationList.declarations[0].name.getText(tree))).map(node => node.getText(tree)).join('\n');
const settings = new Map();
let visible = true, focused = 769, path = '/library/home', sideMenu = false, stops = [], scheduled = 0;
const window = {localStorage: {getItem: key => settings.get(key) ?? null}, SteamUIStore: {MainWindowVisible: {get Value() {return visible;}}, GetWindowForRunningAppNavigation: () => ({get LocationPathName() {return path;}, IsMainGamepadUIWindow: () => true, MenuStore: {IsAnySideMenuVisible: () => sideMenu}})}, FocusedAppWindowStore: {GetFocusedAppID: () => focused}};
const sandbox = {window, console, readAutoPlaySetting: () => true, getLibraryPath: () => path,
  isEligibleRunningAppId: id => id > 0, logClient: () => {}, captureGlobalAmbientResumeSnapshot: () => {},
  stopPlayback: (_, why) => stops.push(why), scheduleAutoPlaybackFromContext: () => scheduled++,
  readAppIdFromRouteSignals: () => null, isStorePath: () => path === '/store', readStoreTrackEnabledSetting: () => true,
  readAmbientDisableStoreSetting: () => false, readGlobalAmbientEnabledSetting: () => true, getGlobalAmbientResumeTime: () => 12,
};
const state = `
const BACKGROUND_MUSIC_STORAGE_KEY='themedeck:allowBackgroundMusic';
let runningGameAppId=null, backgroundLaunchHold=null, runningStateInitialized=false, lastMenuContextSignature='';
let playInvocationCounter=0, playInFlightSignature=null;
const GLOBAL_AMBIENT_APP_ID=-1, STORE_TRACK_APP_ID=-2;
let playbackState={status:'playing',appId:-1,reason:'auto'};
let activeDetailBridgeCount=0, activeDetailRouteAppId=null, launchActivityAppId=null;
let latestTracksForAutoPlay={42:{appId:42,path:'game.m4a'}}, latestGlobalTrackForAutoPlay={path:'ambient.m4a'}, latestStoreTrackForAutoPlay={path:'store.m4a'};
`;
vm.createContext(sandbox);
vm.runInContext(ts.transpileModule(state + functions + `
globalThis.policy={blocked:shouldBlockRunningPlayback, allowed:isBackgroundMenuPlaybackAllowed, running:setRunningGameAppId, changed:refreshMainMenuContext, toggle:handleBackgroundMusicChanged, resolve:resolveAutoTrackFromContext, detail:id=>{activeDetailBridgeCount=id?1:0;activeDetailRouteAppId=id}, launching:id=>{launchActivityAppId=id}};`, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None}}).outputText, sandbox);
const p = sandbox.policy;
p.running(null);
assert.equal(p.blocked(), false);
p.running(42);
assert.equal(p.blocked(), true, 'Default off preserves running-app suppression');
assert.equal(p.resolve(), null);
settings.set('themedeck:allowBackgroundMusic', 'true'); p.toggle();
assert.equal(p.blocked(), false);
assert.equal(p.resolve().path, 'ambient.m4a');
p.launching(99);assert.equal(p.allowed(),false,'A different app still launching must retain launch suppression');
p.launching(null);
p.detail(42); assert.equal(p.resolve().path, 'game.m4a');
p.detail(null); path='/store'; assert.equal(p.resolve().path, 'store.m4a');
p.launching(42); assert.equal(p.resolve().path, 'store.m4a', 'Background running app must not suppress store');
visible=false; focused=42; p.changed();
assert.equal(p.blocked(), true, 'Gameplay blocks music despite stale library route');
assert.equal(p.resolve(), null);
assert.ok(stops.includes('background_music_foreground_change'));
visible=false; focused=769; p.changed();
assert.equal(p.blocked(), true, 'Quick access/overlay is not the full main menu');
visible=true; focused=42; p.changed(); assert.equal(p.blocked(), true);
focused=undefined; p.changed(); assert.equal(p.blocked(), true, 'Unknown focus must block');
focused=769; p.changed(); assert.equal(p.blocked(), false);
sideMenu=true; p.changed(); assert.equal(p.blocked(), true, 'Side overlays cannot restart background music');
sideMenu=false; path='/apprunning';p.changed();assert.equal(p.blocked(),true,'Running-app screen must stay silent even if Steam temporarily has focus');
path='/store';p.changed();assert.equal(p.blocked(),false);
settings.set('themedeck:allowBackgroundMusic','false');p.toggle();assert.equal(p.blocked(),true);
settings.set('themedeck:allowBackgroundMusic','true');p.toggle();
p.running(null);p.launching(99);p.running(99);assert.equal(p.blocked(),true,'New launch holds music even while the old menu remains visible');
visible=false;focused=99;p.changed();assert.equal(p.blocked(),true);
visible=true;focused=769;p.changed();assert.equal(p.blocked(),false,'Returning to menu releases launch hold');
p.running(null);p.launching(100);p.running(100);assert.equal(p.blocked(),true);
path='/library/home';p.changed();assert.equal(p.blocked(),false,'Deliberate menu navigation after launch allows background music');
p.running(null);p.launching(101);assert.equal(p.allowed(),false,'At-launch-finish mode must not mistake a pending launch for a background app');
assert.equal(p.resolve(),null);
assert.ok(scheduled>0);
const play = tree.statements.find(node=>ts.isVariableStatement(node)&&node.declarationList.declarations[0].name.getText(tree)==='playTrack').getText(tree);
assert.equal((play.match(/shouldBlockRunningPlayback\(\)/g)||[]).length,3,'Recheck foreground after asynchronous audio preparation');
assert.ok(source.indexOf('Allow music while games/apps') > source.indexOf('Stop music after pressing Play'));
console.log('Background music default, toggle, foreground/overlay, launch timing, game/global/store selection, and async guard checks passed');
