import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  Spinner,
  ToggleField,
  staticClasses,
  Focusable,
  Router,
  ScrollPanel,
  Navigation,
  useParams,
  afterPatch,
  findInReactTree,
  createReactTreePatcher,
  appDetailsClasses,
  fakeRenderComponent,
  findModuleChild,
  MenuItem,
} from "@decky/ui";
import {
  callable,
  definePlugin,
  routerHook,
  toaster,
} from "@decky/api";
import {
  ReactElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  FaMusic,
  FaPause,
  FaPlay,
  FaTrash,
} from "react-icons/fa";
import { BUILD_LABEL } from "./build-info";

type BackendTrack = {
  app_id: number;
  path: string;
  filename?: string;
  volume?: number;
};

type RawTrackMap = Record<string, BackendTrack>;

type GameTrack = {
  appId: number;
  path: string;
  filename: string;
  volume: number;
};

type TrackMap = Record<number, GameTrack>;
type AudioPayload = {
  data: string;
  mime?: string;
  mtime?: number;
};

type PlaybackReason = "auto" | "manual";

type PlaybackState = {
  appId: number | null;
  reason: PlaybackReason;
  status: "playing" | "stopped";
};

type GameOption = {
  appid: number;
  name: string;
};

type DirectoryListing = {
  path: string;
  dirs: string[];
  files: string[];
};

const GAME_DETAIL_ROUTES = [
  "/library/app/:appid",
  "/library/details/:appid",
  "/library/:collection/app/:appid",
];

const DETAIL_PATTERNS = GAME_DETAIL_ROUTES.map((route) => {
  const pattern = route
    .replace(/\//g, "\\/")
    .replace(":collection", "[^\\/]+")
    .replace(":appid", "(\\d+)");
  return new RegExp(`^${pattern}`);
});

const fetchTracks = callable<[], RawTrackMap>("get_tracks");
const assignTrack = callable<
  [appId: number, path: string, filename: string],
  RawTrackMap
>("set_track");
const deleteTrack = callable<[appId: number], RawTrackMap>("remove_track");
const updateTrackVolume = callable<[appId: number, volume: number], RawTrackMap>(
  "set_volume"
);
const listDirectory = callable<[path?: string], DirectoryListing>("list_directory");
const loadTrackAudio = callable<[path: string], AudioPayload>("load_track_audio");

const TRACKS_UPDATED_EVENT = "themedeck:tracks-updated";
const AUDIO_EXTENSIONS = ["mp3", "aac", "flac", "ogg", "wav", "m4a"];
const AUDIO_EXTENSIONS_LABEL = AUDIO_EXTENSIONS.map((ext) => `.${ext}`).join(
  ", "
);
const AUTO_PLAY_STORAGE_KEY = "themedeck:autoPlay";
const AUTO_PLAY_EVENT = "themedeck:auto-play-changed";

type AudioCacheEntry = {
  objectUrl: string;
  mtime: number;
};

const focusListeners = new Set<(appId: number | null) => void>();
let focusedAppId: number | null = null;
let locationInterval: number | null = null;
let steamAppRetry: number | null = null;
const steamAppSubscriptions: Array<() => void> = [];
const playbackListeners = new Set<(state: PlaybackState) => void>();
let playbackState: PlaybackState = {
  appId: null,
  reason: "auto",
  status: "stopped",
};
let sharedAudio: HTMLAudioElement | null = null;
const audioCache = new Map<string, AudioCacheEntry>();

const readPreference = (key: string, fallback = true): boolean => {
  try {
    const raw = window.localStorage?.getItem(key);
    if (raw === null) {
      return fallback;
    }
    return raw === "true";
  } catch (error) {
    console.error("[ThemeDeck] unable to read preference", { key, error });
    return fallback;
  }
};

const persistPreference = (key: string, event: string, value: boolean) => {
  try {
    window.localStorage?.setItem(key, value ? "true" : "false");
  } catch (error) {
    console.error("[ThemeDeck] unable to store preference", { key, error });
  }
  window.dispatchEvent(new CustomEvent<boolean>(event, { detail: value }));
};

const readAutoPlaySetting = (): boolean =>
  readPreference(AUTO_PLAY_STORAGE_KEY, true);

const persistAutoPlaySetting = (value: boolean) =>
  persistPreference(AUTO_PLAY_STORAGE_KEY, AUTO_PLAY_EVENT, value);

const subscribePlayback = (listener: (state: PlaybackState) => void) => {
  playbackListeners.add(listener);
  return () => {
    playbackListeners.delete(listener);
  };
};

const notifyPlayback = (next: PlaybackState) => {
  playbackState = next;
  playbackListeners.forEach((listener) => {
    try {
      listener(next);
    } catch (error) {
      console.error("[ThemeDeck] playback listener failed", error);
    }
  });
};

const ensureAudio = () => {
  if (!sharedAudio) {
    sharedAudio = new Audio();
    sharedAudio.loop = true;
    sharedAudio.preload = "auto";
  }
  return sharedAudio;
};

const revokeCacheEntry = (path: string) => {
  const cached = audioCache.get(path);
  if (cached) {
    URL.revokeObjectURL(cached.objectUrl);
    audioCache.delete(path);
  }
};

const clearAudioCache = (path?: string) => {
  if (path) {
    revokeCacheEntry(path);
    return;
  }
  for (const entry of audioCache.values()) {
    URL.revokeObjectURL(entry.objectUrl);
  }
  audioCache.clear();
};

const decodePayloadToObjectUrl = (payload: AudioPayload): string => {
  let base64 = payload.data;
  let mime = payload.mime;

  if (base64.startsWith("data:")) {
    const match = base64.match(/^data:([^;]+);base64,(.+)$/);
    if (match) {
      mime = mime ?? match[1];
      base64 = match[2];
    }
  }

  const binary = window.atob(base64);
  const buffer = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    buffer[index] = binary.charCodeAt(index);
  }

  const blob = new Blob([buffer.buffer], {
    type: mime || "audio/mpeg",
  });
  return URL.createObjectURL(blob);
};

const resolveAudioUrl = async (track: GameTrack) => {
  const cached = audioCache.get(track.path);
  if (cached) {
    return cached.objectUrl;
  }
  const payload = await loadTrackAudio(track.path);
  if (!payload?.data) {
    throw new Error("No audio data returned");
  }
  const objectUrl = decodePayloadToObjectUrl(payload);
  audioCache.set(track.path, {
    objectUrl,
    mtime: payload.mtime ?? 0,
  });
  return objectUrl;
};

const stopPlayback = (fade: boolean) => {
  const audio = sharedAudio;
  if (!audio) {
    notifyPlayback({
      appId: null,
      reason: "auto",
      status: "stopped",
    });
    return;
  }

  const finish = () => {
    audio.pause();
    audio.currentTime = 0;
    audio.src = "";
    notifyPlayback({
      appId: null,
      reason: "auto",
      status: "stopped",
    });
  };

  if (!fade || audio.paused) {
    finish();
    return;
  }

  const startingVolume = audio.volume;
  let step = 0;
  const steps = 8;
  const interval = window.setInterval(() => {
    step += 1;
    audio.volume = Math.max(0, startingVolume * (1 - step / steps));
    if (step >= steps) {
      window.clearInterval(interval);
      audio.volume = startingVolume;
      finish();
    }
  }, 40);
};

const playTrack = async (track: GameTrack, reason: PlaybackReason) => {
  const audio = ensureAudio();

  try {
    const nextUrl = await resolveAudioUrl(track);
    const sameTrack =
      playbackState.appId === track.appId &&
      audio.src === nextUrl &&
      playbackState.status === "playing";

    if (!sameTrack) {
      audio.src = nextUrl;
    }

    audio.volume = clamp(track.volume ?? 1);
    await audio.play();
    notifyPlayback({ appId: track.appId, reason, status: "playing" });
  } catch (error) {
    console.error("[ThemeDeck] failed to play", error);
    const message =
      error instanceof Error && error.message
        ? error.message
        : "Unknown playback error";
    toaster.toast({
      title: "ThemeDeck",
      body: `Can't play ${track.filename}: ${message}`,
    });
    stopPlayback(false);
  }
};

const applyVolumeToActiveTrack = (appId: number, volume: number) => {
  if (!sharedAudio) {
    return;
  }
  if (
    playbackState.appId !== appId ||
    playbackState.status !== "playing"
  ) {
    return;
  }
  sharedAudio.volume = clamp(volume);
};

const notifyFocus = (appId: number | null) => {
  focusedAppId = appId;
  focusListeners.forEach((listener) => listener(appId));
};

const getLibraryPath = (): string => {
  try {
    const focusedWindow =
      window.SteamUIStore?.GetFocusedWindowInstance?.() ??
      Router.WindowStore?.GamepadUIMainWindowInstance;
    const browserWindow =
      focusedWindow?.BrowserWindow ??
      Router.WindowStore?.GamepadUIMainWindowInstance?.BrowserWindow;
    return browserWindow?.location?.pathname ?? "";
  } catch (error) {
    console.error("[ThemeDeck] unable to read library window", error);
    return "";
  }
};

const readAppIdFromLocation = (): number | null => {
  const pathname = getLibraryPath();
  for (const pattern of DETAIL_PATTERNS) {
    const match = pathname.match(pattern);
    if (match?.[1]) {
      const parsed = Number.parseInt(match[1], 10);
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
  }
  return null;
};

const startLocationWatcher = () => {
  if (locationInterval) {
    return;
  }
  const update = () => {
    const appId = readAppIdFromLocation();
    if (appId !== focusedAppId) {
      notifyFocus(appId);
    }
  };
  update();
  locationInterval = window.setInterval(update, 750);
};

const stopLocationWatcher = () => {
  if (locationInterval) {
    window.clearInterval(locationInterval);
    locationInterval = null;
  }
};

const extractAppId = (...candidates: any[]): number | null => {
  for (const candidate of candidates) {
    if (typeof candidate === "number" && !Number.isNaN(candidate) && candidate > 0) {
      return candidate;
    }
    if (typeof candidate === "string") {
      const parsed = Number.parseInt(candidate, 10);
      if (!Number.isNaN(parsed)) return parsed;
    }
    if (candidate && typeof candidate === "object") {
      const possible =
        candidate.appid ??
        candidate.app_id ??
        candidate.unAppID ??
        candidate.nAppID ??
        candidate.id;
      if (possible) {
        const parsed = Number.parseInt(possible, 10);
        if (!Number.isNaN(parsed)) return parsed;
      }
    }
  }
  return null;
};

const wrapUnsubscribe = (token: any): (() => void) | null => {
  if (!token) return null;
  if (typeof token === "function") {
    return token;
  }
  if (typeof token.dispose === "function") {
    return () => token.dispose();
  }
  if (typeof token.unregister === "function") {
    return () => token.unregister();
  }
  if (typeof token.Unregister === "function") {
    return () => token.Unregister();
  }
  return null;
};

const startSteamAppWatchers = () => {
  const apps = (window as any)?.SteamClient?.Apps;
  if (!apps) {
    if (steamAppRetry) return;
    steamAppRetry = window.setInterval(() => {
      if (startSteamAppWatchers()) {
        window.clearInterval(steamAppRetry!);
        steamAppRetry = null;
      }
    }, 2000);
    return false;
  }

  const handlers = [
    apps.RegisterForAppDetails?.bind(apps),
    apps.RegisterForAppOverviewChanges?.bind(apps),
  ].filter(Boolean);

  handlers.forEach((registerFn) => {
    try {
      const unsub = registerFn!((...args: any[]) => {
        const candidate = extractAppId(...args);
        if (candidate) {
          notifyFocus(candidate);
        }
      });
      const cleaner = wrapUnsubscribe(unsub);
      if (cleaner) {
        steamAppSubscriptions.push(cleaner);
      }
    } catch (error) {
      console.error("[ThemeDeck] steam app watcher failed", error);
    }
  });

  return handlers.length > 0;
};

const stopSteamAppWatchers = () => {
  steamAppSubscriptions.splice(0).forEach((clean) => {
    try {
      clean();
    } catch (error) {
      console.error("[ThemeDeck] steam app watcher cleanup failed", error);
    }
  });
  if (steamAppRetry) {
    window.clearInterval(steamAppRetry);
    steamAppRetry = null;
  }
};

const resolveLibraryContextMenu = () => {
  try {
    const component = fakeRenderComponent(
      findModuleChild((module: any) => {
        if (!module || typeof module !== "object") return;
        for (const prop in module) {
          const value = module[prop];
          if (
            value?.toString &&
            value.toString().includes("().LibraryContextMenu")
          ) {
            return Object.values(module).find(
              (sibling: any) =>
                sibling?.toString?.().includes("createElement") &&
                sibling.toString().includes("navigator:")
            );
          }
        }
        return;
      })
    );
    return component?.type ?? null;
  } catch (error) {
    console.error("[ThemeDeck] unable to resolve context menu", error);
    return null;
  }
};

const extractAppIdFromTree = (node: any): number | null => {
  if (!node) {
    return null;
  }

  const candidate = extractAppId(
    node?.appid,
    node?.overview?.appid,
    node?._owner?.pendingProps?.overview?.appid,
    node?.props?.overview?.appid
  );
  if (candidate) {
    return candidate;
  }

  const children = node?.children ?? node?.props?.children;
  if (!children) return null;
  if (Array.isArray(children)) {
    for (const child of children) {
      const result = extractAppIdFromTree(child);
      if (result) return result;
    }
  } else {
    return extractAppIdFromTree(children);
  }
  return null;
};

const insertThemeDeckMenu = (children: any, appId: number) => {
  if (!children || !appId) return;

  const list = Array.isArray(children)
    ? children
    : Array.isArray(children?.props?.children)
    ? children.props.children
    : Array.isArray(children?.children)
    ? children.children
    : null;

  if (!Array.isArray(list)) {
    return;
  }

  const existing = list.findIndex(
    (entry) => entry?.key === "themedeck-change-music"
  );
  if (existing !== -1) {
    list.splice(existing, 1);
  }

  const propertiesIdx = list.findIndex((item) =>
    findInReactTree(
      item,
      (node: any) =>
        typeof node?.onSelected === "function" &&
        node.onSelected.toString().includes("AppProperties")
    )
  );

  const menuItem = (
    <MenuItem
      key="themedeck-change-music"
      onSelected={() => {
        Navigation.CloseSideMenus?.();
        Navigation.Navigate(`/themedeck/${appId}`);
      }}
    >
      Choose ThemeDeck music...
    </MenuItem>
  );

  if (propertiesIdx >= 0) {
    list.splice(propertiesIdx, 0, menuItem);
  } else {
    list.push(menuItem);
  }
};

const patchContextMenuFocus = () => {
  const MenuComponent = resolveLibraryContextMenu();
  if (!MenuComponent) {
    return null;
  }

  const patches: {
    outer?: { unpatch: () => void };
    inner?: { unpatch: () => void };
  } = {};

  patches.outer = afterPatch(
    MenuComponent.prototype,
    "render",
    (_args: Record<string, unknown>[], component: any) => {
      const baseAppId = extractAppId(
        component?._owner?.pendingProps?.overview?.appid
      );
      if (baseAppId) {
        notifyFocus(baseAppId);
        insertThemeDeckMenu(component?.props?.children, baseAppId);
      }

      if (!patches.inner && component?.type?.prototype) {
        patches.inner = afterPatch(
          component.type.prototype,
          "shouldComponentUpdate",
          ([nextProps]: any, shouldUpdate: any) => {
            const derived = extractAppIdFromTree({
              children: nextProps?.children,
              overview: nextProps?.overview,
            });
            if (derived) {
              notifyFocus(derived);
              insertThemeDeckMenu(nextProps?.children, derived);
            }
            return shouldUpdate;
          }
        );
      } else {
        const derived = extractAppIdFromTree(component);
        if (derived) {
          notifyFocus(derived);
          insertThemeDeckMenu(component?.props?.children, derived);
        }
      }

      return component;
    }
  );

  return () => {
    patches.outer?.unpatch();
    patches.inner?.unpatch();
  };
};

const injectBridgeIntoRoute = (routePattern: string) =>
  routerHook.addPatch(routePattern, (tree: any) => {
    const routeProps = findInReactTree(tree, (node) => node?.renderFunc);
    if (!routeProps) {
      return tree;
    }

    const handler = createReactTreePatcher(
      [
        (input) =>
          findInReactTree(
            input,
            (x: any) => x?.props?.children?.props?.overview
          )?.props?.children,
      ],
      (_: Array<Record<string, unknown>>, ret?: ReactElement) => {
        const container = findInReactTree(
          ret,
          (x: any) =>
            Array.isArray(x?.props?.children) &&
            typeof x?.props?.className === "string" &&
            x.props.className.includes(appDetailsClasses.InnerContainer)
        );

        if (
          !container ||
          !Array.isArray(container.props.children) ||
          container.props.children.some(
            (child: any) => child?.key === "themedeck-bridge"
          )
        ) {
          return ret;
        }

        container.props.children = [
          ...container.props.children,
          <GameFocusBridge key="themedeck-bridge" />,
        ];

        return ret;
      }
    );

    afterPatch(routeProps, "renderFunc", handler);
    return tree;
  });

const GameFocusBridge = () => {
  const params = useParams<{ appid?: string }>();
  const parsed = params?.appid ? Number.parseInt(params.appid, 10) : NaN;
  const appId = Number.isNaN(parsed) ? null : parsed;
  const { tracks } = useTrackState({ silent: true });
  const autoPlayEnabled = useAutoPlayValue();
  const playback = usePlaybackStateValue();

  useEffect(() => {
    notifyFocus(appId);
    return () => {
      notifyFocus(null);
      if (
        playbackState.reason === "auto" &&
        playbackState.status === "playing"
      ) {
        stopPlayback(true);
      }
    };
  }, [appId]);

  useEffect(() => {
    if (!autoPlayEnabled) {
      if (playback.reason === "auto") {
        stopPlayback(true);
      }
      return;
    }

    if (!appId) {
      if (playback.reason === "auto") {
        stopPlayback(true);
      }
      return;
    }

    const track = tracks[appId];
    if (!track) {
      if (playback.reason === "auto") {
        stopPlayback(true);
      }
      return;
    }

    if (playback.reason === "manual") {
      return;
    }

    playTrack(track, "auto");
  }, [autoPlayEnabled, appId, tracks, playback.reason]);

  return null;
};

const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value));

const normalizeTracks = (raw: RawTrackMap | null | undefined): TrackMap => {
  const normalized: TrackMap = {};
  if (!raw) {
    return normalized;
  }

  for (const [key, track] of Object.entries(raw)) {
    if (!track) continue;
    const idFromKey = Number.parseInt(key, 10);
    const appId = Number.isNaN(idFromKey) ? track.app_id : idFromKey;
    if (appId === undefined || appId === null || Number.isNaN(appId)) continue;

    normalized[appId] = {
      appId,
      path: track.path,
      filename:
        track.filename ||
        track.path?.split("/").pop() ||
        `Track ${appId}`,
      volume:
        typeof track.volume === "number" ? clamp(track.volume) : 1,
    };
  }

  return normalized;
};

const useTrackState = (options?: { silent?: boolean }) => {
  const [tracks, setTracks] = useState<TrackMap>({});
  const [loadingTracks, setLoadingTracks] = useState(true);
  const silent = options?.silent ?? false;

  const refreshTracks = useCallback(async () => {
    try {
      const data = await fetchTracks();
      setTracks(normalizeTracks(data));
    } catch (error) {
      console.error("[ThemeDeck] load tracks failed", error);
      if (!silent) {
        toaster.toast({
          title: "ThemeDeck",
          body: "Failed to load saved tracks",
        });
      }
    } finally {
      setLoadingTracks(false);
    }
  }, [silent]);

  useEffect(() => {
    refreshTracks();
  }, [refreshTracks]);

  useEffect(() => {
    const handler = () => {
      clearAudioCache();
      refreshTracks();
    };
    window.addEventListener(TRACKS_UPDATED_EVENT, handler);
    return () =>
      window.removeEventListener(TRACKS_UPDATED_EVENT, handler);
  }, [refreshTracks]);

  return { tracks, setTracks, loadingTracks, refreshTracks };
};

const getDisplayName = (appId: number) => {
  const store = (window as any)?.appStore;
  const overview =
    store?.GetAppOverviewByAppID?.(appId) ||
    store?.GetAppOverviewByGameID?.(appId);
  return (
    overview?.display_name ||
    overview?.localized_name ||
    overview?.name ||
    `App ${appId}`
  );
};

const usePlaybackStateValue = () => {
  const [state, setState] = useState<PlaybackState>(playbackState);
  useEffect(() => subscribePlayback(setState), []);
  return state;
};

const useBooleanPreference = (
  readFn: () => boolean,
  persistFn: (value: boolean) => void,
  eventName: string
): [boolean, (value: boolean) => void] => {
  const [value, setValue] = useState<boolean>(() => readFn());

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail;
      if (typeof detail === "boolean") {
        setValue(detail);
        return;
      }
      setValue(readFn());
    };
    window.addEventListener(eventName, handler as EventListener);
    return () =>
      window.removeEventListener(eventName, handler as EventListener);
  }, [readFn, eventName]);

  const update = useCallback(
    (next: boolean) => {
      setValue(next);
      persistFn(next);
    },
    [persistFn]
  );

  return [value, update];
};

const useAutoPlaySetting = (): [boolean, (value: boolean) => void] =>
  useBooleanPreference(
    readAutoPlaySetting,
    persistAutoPlaySetting,
    AUTO_PLAY_EVENT
  );

const useAutoPlayValue = () => {
  const [value, setValue] = useState<boolean>(() => readAutoPlaySetting());

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail;
      if (typeof detail === "boolean") {
        setValue(detail);
        return;
      }
      setValue(readAutoPlaySetting());
    };
    window.addEventListener(AUTO_PLAY_EVENT, handler as EventListener);
    return () => window.removeEventListener(AUTO_PLAY_EVENT, handler as EventListener);
  }, []);

  return value;
};

const Content = () => {
  const { tracks, setTracks, loadingTracks } = useTrackState();
  const [library, setLibrary] = useState<GameOption[]>([]);
  const [autoPlay, setAutoPlay] = useAutoPlaySetting();
  const [pendingRemoval, setPendingRemoval] = useState<number | null>(null);
  const playback = usePlaybackStateValue();
  const topFocusRef = useRef<HTMLDivElement | null>(null);
  const getGameName = useCallback(
    (appId: number) => {
      const store = (window as any)?.appStore;
      const overview = store?.GetAppOverviewByAppID?.(appId);
      return (
        overview?.display_name ||
        overview?.localized_name ||
        overview?.name ||
        library.find((game) => game.appid === appId)?.name ||
        tracks[appId]?.filename ||
        getDisplayName(appId)
      );
    },
    [tracks, library]
  );
  const gameTracks = useMemo(
    () =>
      Object.values(tracks)
        .sort((a, b) => getGameName(a.appId).localeCompare(getGameName(b.appId))),
    [tracks, getGameName]
  );

  const loadLibrary = useCallback(() => {
    try {
      const bootstrap =
        (window as any)?.SteamClient?.Apps?.GetLibraryBootstrapData?.() ??
        (window as any)?.appStore?.GetLibraryBootstrapData?.();
      if (!bootstrap) return;
      const rawApps =
        bootstrap?.library?.apps ||
        bootstrap?.apps ||
        bootstrap?.rgApps ||
        [];
      const values: any[] = Array.isArray(rawApps)
        ? rawApps
        : Object.values(rawApps);
      const games: GameOption[] = values
        .map((entry) => {
          const appid =
            entry?.appid ??
            entry?.app_id ??
            entry?.unAppID ??
            entry?.nAppID;
          if (!appid) return null;
          return {
            appid: Number(appid),
            name:
              entry?.display_name ||
              entry?.localized_name ||
              entry?.name ||
              entry?.strTitle ||
              `App ${appid}`,
          };
        })
        .filter((entry): entry is GameOption => !!entry)
        .sort((a, b) => a.name.localeCompare(b.name));
      setLibrary(games);
    } catch (error) {
      console.error("[ThemeDeck] library load failed", error);
    }
  }, []);

  useEffect(() => {
    loadLibrary();
  }, [loadLibrary]);

  const removeTrack = async (appId: number) => {
    try {
      const removedPath = tracks[appId]?.path;
      const updated = await deleteTrack(appId);
      setTracks(normalizeTracks(updated));
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      if (removedPath) {
        clearAudioCache(removedPath);
      }
      if (playback.appId === appId) {
        stopPlayback(true);
      }
    } catch (error) {
      console.error("[ThemeDeck] remove failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Failed to remove track",
      });
    }
  };
  const requestRemove = (track: GameTrack) => {
    setPendingRemoval(track.appId);
  };

  const cancelRemove = () => setPendingRemoval(null);

  const confirmRemove = async (appId: number) => {
    try {
      await removeTrack(appId);
    } finally {
      setPendingRemoval(null);
    }
  };

  const handlePreviewToggle = (track: GameTrack) => {
    if (playback.appId === track.appId && playback.status === "playing") {
      stopPlayback(false);
      return;
    }
    playTrack(track, "manual");
  };

  const handleVolumeChange = async (appId: number, value: number) => {
    const normalizedVolume = clamp(value / 100);
    setTracks((prev) => ({
      ...prev,
      [appId]: {
        ...prev[appId],
        volume: normalizedVolume,
      },
    }));
    applyVolumeToActiveTrack(appId, normalizedVolume);

    try {
      const updated = await updateTrackVolume(appId, normalizedVolume);
      setTracks(normalizeTracks(updated));
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
    } catch (error) {
      console.error("[ThemeDeck] volume update failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Couldn't save volume",
      });
    }
  };

  useEffect(() => {
    topFocusRef.current?.focus();
  }, []);

  return (
    <ScrollPanel>
      <div style={{ paddingBottom: "1.5rem" }}>
      <div
        ref={topFocusRef}
        tabIndex={-1}
        style={{ position: "absolute", width: 0, height: 0, outline: "none" }}
      />
      <PanelSection>
        <PanelSectionRow>
          <div style={{ width: "100%", paddingTop: "0.2rem" }}>
            <div style={{ fontSize: "0.9rem", opacity: 0.8 }}>
              {BUILD_LABEL}
            </div>
            <hr style={{ margin: "0.4rem 0" }} />
          </div>
        </PanelSectionRow>
      </PanelSection>
      <div style={{ marginTop: "-0.35rem" }}>
        <PanelSection title="Instructions">
          <PanelSectionRow>
            <Focusable style={{ width: "100%", paddingBottom: "0.4rem" }}>
              To assign music to a game page, open that game's details screen,
              choose <em>Settings</em>, then select <em>Choose ThemeDeck music…</em> to
              browse for a local file.
              <br />
              <br />
              Supported formats include {AUDIO_EXTENSIONS_LABEL}.
            </Focusable>
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              checked={autoPlay}
              label="Auto play on game page"
              description="Start music as soon as you open a game's details view."
              onChange={(value) => setAutoPlay(value)}
            />
          </PanelSectionRow>
        </PanelSection>
      </div><PanelSection title="Assigned tracks">
        {loadingTracks ? (
          <PanelSectionRow>
            <Spinner />
          </PanelSectionRow>
        ) : gameTracks.length === 0 ? (
          <PanelSectionRow>
            <div>No games have music yet.</div>
          </PanelSectionRow>
        ) : (
          gameTracks.map((track) => (
            <PanelSectionRow key={track.appId}>
              <Focusable style={{ width: "100%" }}>
                <div style={{ fontWeight: 600 }}>
                  {getGameName(track.appId)}
                </div>
                <div style={{ opacity: 0.8, fontSize: "0.9rem" }}>
                  {track.filename}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: "0.5rem",
                    marginTop: "0.5rem",
                    flexWrap: "nowrap",
                  }}
                >
                  <button
                    className="DialogButton"
                    style={{
                      width: "3rem",
                      height: "2.6rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 0,
                    }}
                    title={
                      playback.appId === track.appId &&
                      playback.status === "playing"
                        ? "Pause preview"
                        : "Preview track"
                    }
                    onClick={() => handlePreviewToggle(track)}
                  >
                    {playback.appId === track.appId &&
                    playback.status === "playing" ? (
                      <FaPause />
                    ) : (
                      <FaPlay />
                    )}
                  </button>
                  <button
                    className="DialogButton"
                    style={{
                      width: "3rem",
                      height: "2.6rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 0,
                    }}
                    title={`Remove music from ${getGameName(track.appId)}`}
                    onClick={() => requestRemove(track)}
                  >
                    <FaTrash />
                  </button>
                </div>
                {pendingRemoval === track.appId && (
                  <div
                    style={{
                      marginTop: "0.5rem",
                      padding: "0.6rem",
                      borderRadius: "0.4rem",
                      background: "rgba(255,255,255,0.05)",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.45rem",
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>
                      Remove "{track.filename}"?
                    </div>
                    <div
                      style={{
                        display: "flex",
                        gap: "0.6rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <button
                        className="DialogButton"
                        onClick={() => confirmRemove(track.appId)}
                        style={{ flex: "0 0 5.5rem" }}
                      >
                        Confirm
                      </button>
                      <button
                        className="DialogButton"
                        onClick={cancelRemove}
                        style={{ flex: "0 0 5.5rem" }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                <div style={{ marginTop: "0.5rem", paddingRight: "1.25rem" }}>
                  <SliderField
                    value={Math.round(track.volume * 100)}
                    label="Game playback volume"
                    min={0}
                    max={100}
                    step={5}
                    valueSuffix="%"
                    showValue
                    onChange={(value) =>
                      handleVolumeChange(track.appId, value)
                    }
                  />
                </div>
              </Focusable>
            </PanelSectionRow>
          ))
        )}
      </PanelSection>
      </div>
    </ScrollPanel>
  );
};

const ChangeTheme = () => {
  const params = useParams<{ appid?: string }>();
  const appId = Number(params?.appid);
  const [track, setTrack] = useState<GameTrack | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentDir, setCurrentDir] = useState("/home/deck");
  const [browser, setBrowser] = useState<DirectoryListing>({
    path: "/home/deck",
    dirs: [],
    files: [],
  });
  const [browserLoading, setBrowserLoading] = useState(true);
  const [manualPath, setManualPath] = useState("/home/deck");

  const loadTrack = useCallback(async () => {
    if (!appId) return;
    setLoading(true);
    try {
      const data = await fetchTracks();
      const normalized = normalizeTracks(data);
      setTrack(normalized[appId] ?? null);
    } catch (error) {
      console.error("[ThemeDeck] failed to load track", error);
    } finally {
      setLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    loadTrack();
  }, [loadTrack]);

  const refreshDirectory = useCallback(
    async (nextDir?: string) => {
      if (!appId) return;
      setBrowserLoading(true);
      try {
        const listing = await listDirectory(nextDir || currentDir);
        setBrowser(listing);
        setCurrentDir(listing.path);
        setManualPath(listing.path);
      } catch (error) {
        console.error("[ThemeDeck] list directory failed", error);
      } finally {
        setBrowserLoading(false);
      }
    },
    [appId, currentDir]
  );

  useEffect(() => {
    refreshDirectory("/home/deck");
  }, []);

  const saveFromPath = async (fullPath: string) => {
    if (!appId) return;
    try {
      const filename = fullPath.split("/").pop() || "track";
      await assignTrack(appId, fullPath, filename);
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      await loadTrack();
      toaster.toast({
        title: "ThemeDeck",
        body: `Saved music for ${getDisplayName(appId)}`,
      });
    } catch (error) {
      console.error("[ThemeDeck] save from path failed", error);
      const message =
        error instanceof Error && error.message
          ? error.message
          : "Unable to add that file";
      console.error("[ThemeDeck] save from path detailed error", {
        app: appId,
        message,
        error,
        fullPath,
      });
      toaster.toast({
        title: "ThemeDeck",
        body: `Unable to add file (${fullPath}): ${message}`,
      });
    }
  };

  const joinPath = (base: string, child: string) =>
    base === "/" ? `/${child}` : `${base.replace(/\/$/, "")}/${child}`;

  const goUp = () => {
    if (currentDir === "/") return;
    const parent = currentDir.replace(/\/[^/]+$/, "") || "/";
    refreshDirectory(parent);
  };

  const handleDirClick = (dir: string) => {
    refreshDirectory(joinPath(currentDir, dir));
  };

  const handleFileClick = (file: string) => {
    saveFromPath(joinPath(currentDir, file));
  };

  const handleManualGo = () => {
    if (!manualPath) return;
    refreshDirectory(manualPath);
  };


  const handleRemove = async () => {
    if (!appId) return;
    try {
      await deleteTrack(appId);
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      setTrack(null);
      toaster.toast({
        title: "ThemeDeck",
        body: `Cleared music for ${getDisplayName(appId)}`,
      });
    } catch (error) {
      console.error("[ThemeDeck] route remove failed", error);
    }
  };

  if (!appId) {
    return (
      <ScrollPanel>
        <div style={{ padding: 24, paddingBottom: 120 }}>
          <PanelSection title="ThemeDeck">
            <PanelSectionRow>Invalid game id.</PanelSectionRow>
          </PanelSection>
        </div>
      </ScrollPanel>
    );
  }

  return (
    <ScrollPanel>
      <div
        style={{
          padding: 24,
          paddingTop: 48,
          paddingBottom: 140,
          minHeight: "100vh",
          boxSizing: "border-box",
        }}
      >
      <PanelSection title={`ThemeDeck for ${getDisplayName(appId)}`}>
        <PanelSectionRow>
          {loading ? (
            <Spinner />
          ) : track ? (
            <div>
              <div style={{ fontWeight: 600 }}>{track.filename}</div>
              <div style={{ opacity: 0.8 }}>{track.path}</div>
            </div>
          ) : (
            <div>No music selected yet.</div>
          )}
        </PanelSectionRow>
        <PanelSectionRow>
          {track && (
            <ButtonItem layout="inline" onClick={handleRemove}>
              Remove music
            </ButtonItem>
          )}
          <ButtonItem layout="inline" onClick={() => Navigation.NavigateBack()}>
            Done
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Browse local files">
        <PanelSectionRow>
          <div
            style={{
              display: "flex",
              width: "100%",
              gap: "0.5rem",
              alignItems: "center",
            }}
          >
            <button className="DialogButton" onClick={goUp}>
              Up
            </button>
            <div style={{ flexGrow: 1, fontFamily: "monospace" }}>
              {currentDir}
            </div>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div
            style={{
              display: "flex",
              width: "100%",
              gap: "0.5rem",
              alignItems: "center",
            }}
          >
            <input
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              style={{ flexGrow: 1 }}
            />
            <button className="DialogButton" onClick={handleManualGo}>
              Go
            </button>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          {browserLoading ? (
            <Spinner />
          ) : (
            <div
              style={{
                width: "100%",
                display: "flex",
                flexDirection: "column",
                gap: "0.35rem",
                paddingRight: "0.25rem",
              }}
            >
              {browser.dirs.map((dir) => (
                <button
                  key={`dir-${dir}`}
                  className="DialogButton"
                  onClick={() => handleDirClick(dir)}
                  style={{ justifyContent: "flex-start" }}
                >
                  📁 {dir}
                </button>
              ))}
              {browser.files
                .filter((file) =>
                  AUDIO_EXTENSIONS.some((ext) =>
                    file.toLowerCase().endsWith(`.${ext}`)
                  )
                )
                .map((file) => (
                  <button
                    key={`file-${file}`}
                    className="DialogButton"
                    onClick={() => handleFileClick(file)}
                    style={{ justifyContent: "flex-start" }}
                  >
                    🎵 {file}
                  </button>
                ))}
              {!browser.dirs.length && !browser.files.length && (
                <div style={{ opacity: 0.6 }}>Folder is empty.</div>
              )}
            </div>
          )}
        </PanelSectionRow>
      </PanelSection>
      </div>
    </ScrollPanel>
  );
};

export default definePlugin(() => {
  startLocationWatcher();
  startSteamAppWatchers();
  const gamePatches = GAME_DETAIL_ROUTES.map((path) =>
    injectBridgeIntoRoute(path)
  );
  const contextMenuUnpatch = patchContextMenuFocus();
  routerHook.addRoute(
    "/themedeck/:appid",
    () => <ChangeTheme />,
    { exact: true }
  );

  return {
    name: "ThemeDeck",
    titleView: (
      <div className={staticClasses.Title}>ThemeDeck</div>
    ),
    icon: <FaMusic />,
    content: <Content />,
    onDismount() {
      stopLocationWatcher();
      stopSteamAppWatchers();
      stopPlayback(false);
      clearAudioCache();
      contextMenuUnpatch?.();
      gamePatches.forEach((patch, index) => {
        try {
          routerHook.removePatch(GAME_DETAIL_ROUTES[index], patch);
        } catch (error) {
          console.error("[ThemeDeck] remove patch failed", error);
        }
      });
      try {
        routerHook.removeRoute("/themedeck/:appid");
      } catch (error) {
        console.error("[ThemeDeck] remove route failed", error);
      }
    },
  };
});
