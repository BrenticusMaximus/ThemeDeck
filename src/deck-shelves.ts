// Structural subset of the public @deck-shelves/api contract.
// Runtime globals avoid making Deck Shelves an installation requirement.
type Track = { app_id?: number; path: string; assigned_at?: number };
type Tracks = Record<string, Track>;
type Off = () => void;
type ShelfApi = {
  version: number;
  registerShelfSource(d: { id: string; label: string; resolve(limit: number): Promise<number[]> }): Off;
  registerFilterType(d: { id: string; label: string; invertible: boolean; evaluate(app: { appid: number }): boolean }): Off;
  registerSortOption(d: { id: string; label: string; sort(ids: readonly number[], apps: readonly unknown[]): number[] }): Off;
  getShelves(): readonly { id: string }[];
  getSmartShelves(): readonly { id: string }[];
  refreshShelf(id: string): void;
};
type Integration = { name: string; version: string; onMount(api: ShelfApi): void; onUnmount(): void };
type Host = { register(integration: Integration): Off };

let assignments = new Map<number, number>();
let activeApi: ShelfApi | undefined;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let loaded = false;

const refresh = () => {
  if (!activeApi || refreshTimer) return;
  refreshTimer = setTimeout(() => {
    refreshTimer = undefined;
    try {
      // Filters may be nested or saved, so refresh both shelf collections.
      const ids = new Set([...activeApi!.getShelves(), ...activeApi!.getSmartShelves()].map(s => s.id));
      ids.forEach(id => activeApi!.refreshShelf(id));
    } catch (error) { console.warn('[ThemeDeck] Shelf refresh failed', error); }
  }, 250);
};

export const updateShelfAssignments = (tracks: Tracks) => {
  const next = new Map<number, number>();
  for (const [key, track] of Object.entries(tracks)) {
    // Reserved global/store keys must never become game assignments.
    if (!/^\d+$/.test(key) || !track?.path) continue;
    const id = Number(key);
    if (!Number.isSafeInteger(id) || id <= 0) continue;
    next.set(id, typeof track.assigned_at === 'number' && Number.isFinite(track.assigned_at) ? track.assigned_at : 0);
  }
  const changed = !loaded || next.size !== assignments.size || [...next].some(([id, date]) => assignments.get(id) !== date);
  assignments = next;
  loaded = true;
  if (changed) refresh();
};

export const sortRecentlyAssigned = (ids: readonly number[]) => [...ids].sort((a, b) => {
  const aHas = assignments.has(a), bHas = assignments.has(b);
  if (aHas !== bHas) return aHas ? -1 : 1;
  return (assignments.get(b) ?? 0) - (assignments.get(a) ?? 0) || a - b;
});

export const startDeckShelvesIntegration = (
  fetchTracks: () => Promise<Tracks>,
  fetchLibrary: () => Promise<{ games?: { appid: number }[] }>,
): Off => {
  let disposed = false;
  let offHost: Off | undefined;
  let registrations: Off[] = [];
  let generation = 0;
  const clear = () => {
    generation++;
    activeApi = undefined;
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = undefined;
    registrations.splice(0).reverse().forEach(off => off());
  };
  const integration: Integration = {
    name: 'ThemeDeck', version: '3.1.1',
    onMount(api) {
      clear();
      if (disposed || api.version < 3) return;
      activeApi = api;
      const current = generation;
      const sync = async () => {
        const tracks = await fetchTracks();
        if (!disposed && generation === current) updateShelfAssignments(tracks);
      };
      for (const [mode, label] of [
        ['with-music', 'ThemeDeck: Games with music'],
        ['without-music', 'ThemeDeck: Games without music'],
        ['recent-music', 'ThemeDeck: Recently assigned music'],
      ]) {
        registrations.push(api.registerShelfSource({
          id: `themedeck.${mode}`, label,
          async resolve(limit) {
            await sync();
            if (disposed || generation !== current) return [];
            let ids: number[];
            if (mode === 'without-music') {
              const library = await fetchLibrary();
              if (disposed || generation !== current) return [];
              const libraryIds = new Set((library.games ?? []).map(g => g.appid));
              // Include unplayed games and non-Steam shortcuts in Steam's live library.
              const store = (window as unknown as { appStore?: { m_mapAppOverview?: Map<number, { appid?: number; app_type?: number }> } }).appStore;
              store?.m_mapAppOverview?.forEach((app, id) => {
                if (app.app_type === 1 || app.app_type === 1073741824) libraryIds.add(app.appid ?? id);
              });
              ids = [...libraryIds].filter(id => Number.isSafeInteger(id) && id > 0 && !assignments.has(id));
            } else ids = [...assignments.keys()];
            ids = mode === 'recent-music' ? sortRecentlyAssigned(ids) : ids.sort((a, b) => a - b);
            return ids.slice(0, Math.max(0, limit));
          },
        }));
      }
      for (const hasMusic of [true, false]) registrations.push(api.registerFilterType({
        id: `themedeck.${hasMusic ? 'has-music' : 'no-music'}`,
        label: `ThemeDeck: ${hasMusic ? 'Has music assigned' : 'Has no music assigned'}`,
        invertible: true,
        evaluate: app => loaded && assignments.has(app.appid) === hasMusic,
      }));
      registrations.push(api.registerSortOption({
        id: 'themedeck.recent-music', label: 'ThemeDeck: Most recently assigned music',
        sort: ids => sortRecentlyAssigned(ids),
      }));
      void sync().catch(error => console.warn('[ThemeDeck] Could not load shelf assignments', error));
    },
    onUnmount: clear,
  };
  const attach = () => {
    if (disposed || offHost) return;
    const host = (window as unknown as { deckShelves?: Host }).deckShelves;
    if (!host) return;
    try { offHost = host.register(integration); }
    catch (error) { clear(); console.warn('[ThemeDeck] Deck Shelves registration failed', error); }
  };
  const teardown = () => { offHost = undefined; clear(); };
  window.addEventListener('deck-shelves:ready', attach);
  window.addEventListener('deck-shelves:teardown', teardown);
  attach();
  return () => {
    disposed = true;
    window.removeEventListener('deck-shelves:ready', attach);
    window.removeEventListener('deck-shelves:teardown', teardown);
    offHost?.();
    offHost = undefined;
    clear();
    assignments.clear();
    loaded = false;
  };
};
