import {
  PanelSection,
  PanelSectionRow,
  SliderField,
  Spinner,
  TextField,
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
  Patch,
  findInTree,
} from "@decky/ui";
import {
  callable,
  definePlugin,
  executeInTab,
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

type BackendTrack = {
  app_id?: number;
  path: string;
  filename?: string;
  volume?: number;
  start_offset?: number;
};

type RawTrackMap = Record<string, BackendTrack>;

type GameTrack = {
  appId: number;
  path: string;
  filename: string;
  volume: number;
  startOffset: number;
  resumeTime?: number;
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

type YouTubeSearchResult = {
  id: string;
  title: string;
  uploader?: string;
  duration?: number | null;
  webpage_url: string;
};

type YouTubeSearchResponse = {
  results: YouTubeSearchResult[];
};

type YouTubeDownloadResponse = {
  tracks: RawTrackMap;
  path: string;
  filename: string;
};

type YouTubePreviewResponse = {
  stream_url: string;
};

type GlobalTrack = {
  path: string;
  filename: string;
  volume: number;
  startOffset: number;
};
type StoreTrack = GlobalTrack;
type AmbientInterruptionMode = "stop" | "pause" | "mute";
type LaunchStopMode = "launch_start" | "game_started";

type YtDlpStatus = {
  installed: boolean;
  path?: string;
  source?: string;
  version?: string;
};

type BulkAssignStatus = {
  running: boolean;
  stopRequested: boolean;
  total: number;
  completed: number;
  assigned: number;
  skipped: number;
  failed: number;
  currentGame: string;
  message: string;
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
const fetchGlobalTrack = callable<[], BackendTrack | null>("get_global_track");
const fetchStoreTrack = callable<[], BackendTrack | null>("get_store_track");
const fetchLocalconfigAppIds = callable<[], { app_ids?: number[] }>(
  "get_localconfig_app_ids"
);
const resolveStoreAppNames = callable<
  [appIds: number[]],
  Record<string, string>
>("resolve_store_app_names");
const assignTrack = callable<
  [appId: number, path: string, filename: string],
  RawTrackMap
>("set_track");
const assignGlobalTrack = callable<[path: string, filename: string], BackendTrack>(
  "set_global_track"
);
const assignStoreTrack = callable<[path: string, filename: string], BackendTrack>(
  "set_store_track"
);
const deleteTrack = callable<[appId: number], RawTrackMap>("remove_track");
const deleteGlobalTrack = callable<[], RawTrackMap>("remove_global_track");
const deleteStoreTrack = callable<[], RawTrackMap>("remove_store_track");
const updateTrackVolume = callable<[appId: number, volume: number], RawTrackMap>(
  "set_volume"
);
const updateGlobalVolume = callable<[volume: number], BackendTrack>(
  "set_global_volume"
);
const updateStoreVolume = callable<[volume: number], BackendTrack>(
  "set_store_volume"
);
const updateTrackStartOffset = callable<
  [appId: number, startOffset: number],
  RawTrackMap
>("set_start_offset");
const updateGlobalStartOffset = callable<[startOffset: number], BackendTrack>(
  "set_global_start_offset"
);
const updateStoreStartOffset = callable<[startOffset: number], BackendTrack>(
  "set_store_start_offset"
);
const listDirectory = callable<[path?: string], DirectoryListing>("list_directory");
const loadTrackAudio = callable<[path: string], AudioPayload>("load_track_audio");
const searchYouTube = callable<
  [query: string, limit?: number],
  YouTubeSearchResponse
>("search_youtube");
const downloadYouTubeAudio = callable<
  [appId: number, videoUrl: string],
  YouTubeDownloadResponse
>("download_youtube_audio");
const getYouTubePreviewStream = callable<
  [videoUrl: string],
  YouTubePreviewResponse
>("get_youtube_preview_stream");
const getYtDlpStatus = callable<[], YtDlpStatus>("get_yt_dlp_status");
const updateYtDlp = callable<[], YtDlpStatus>("update_yt_dlp");

const TRACKS_UPDATED_EVENT = "themedeck:tracks-updated";
const AUDIO_EXTENSIONS = ["mp3", "aac", "flac", "ogg", "wav", "m4a"];
const AUTO_PLAY_STORAGE_KEY = "themedeck:autoPlay";
const AUTO_PLAY_EVENT = "themedeck:auto-play-changed";
const GLOBAL_AMBIENT_ENABLED_STORAGE_KEY = "themedeck:globalAmbientEnabled";
const GLOBAL_AMBIENT_ENABLED_EVENT = "themedeck:global-ambient-enabled-changed";
const STORE_TRACK_ENABLED_STORAGE_KEY = "themedeck:storeTrackEnabled";
const STORE_TRACK_ENABLED_EVENT = "themedeck:store-track-enabled-changed";
const AMBIENT_DISABLE_STORE_STORAGE_KEY = "themedeck:ambientDisableStore";
const AMBIENT_DISABLE_STORE_EVENT = "themedeck:ambient-disable-store-changed";
const AMBIENT_INTERRUPTION_MODE_STORAGE_KEY =
  "themedeck:ambientInterruptionMode";
const AMBIENT_INTERRUPTION_MODE_EVENT =
  "themedeck:ambient-interruption-mode-changed";
const LAUNCH_STOP_MODE_STORAGE_KEY = "themedeck:launchStopMode";
const LAUNCH_STOP_MODE_EVENT = "themedeck:launch-stop-mode-changed";
const GLOBAL_AMBIENT_APP_ID = -1;
const STORE_TRACK_APP_ID = -2;
const UI_MODE_GAMEPAD = 4;
const UI_MODE_DESKTOP = 7;
const UI_MODE_POLL_MS = 2000;
const UI_MODE_CACHE_MS = 1000;
const RUNNING_APP_POLL_MS = 1250;
const SP_TAB_CANDIDATES = [
  "SP",
  "sp",
  "SharedJSContext",
  "Steam",
  "SteamUI",
  "MainMenu",
  "GamepadUI",
  "Library",
] as const;
const LIBRARY_EXCLUDED_APP_IDS = new Set<number>([
  7, // Steam client
  760, // Steam screenshots/uploader component
  12210, // Steam Linux runtime/tool entries
  12211,
  12212,
  12213,
  12218,
  228980, // Steamworks Common Redistributables
]);

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
let latestTracksForAutoPlay: TrackMap = {};
let latestGlobalTrackForAutoPlay: GlobalTrack | null = null;
let latestStoreTrackForAutoPlay: StoreTrack | null = null;
let autoPlaybackTick: number | null = null;
let autoPlaybackStarted = false;
let stopAutoPlaybackSubscription: (() => void) | null = null;
let autoPlaybackTrackRefreshInFlight = false;
let autoPlaybackRouteInterval: number | null = null;
let autoPlaybackStoreProbeInFlight = false;
let storeContextActive = false;
let playInvocationCounter = 0;
let playInFlightSignature: string | null = null;
let desktopModeActive = false;
let desktopModeLastCheck = 0;
let desktopModeRefreshInFlight: Promise<boolean> | null = null;
let uiModePollInterval: number | null = null;
let stopUIModeSubscription: (() => void) | null = null;
let runningGameAppId: number | null = null;
let runningAppPollInterval: number | null = null;
let runningAppRetry: number | null = null;
let runningAppRefreshInFlight = false;
const runningAppSubscriptions: Array<() => void> = [];
let launchStopModeRuntime: LaunchStopMode = "launch_start";
let globalAmbientResumeSnapshot: {
  path: string;
  seconds: number;
  capturedAtMs: number;
  durationSeconds: number | null;
  mode: AmbientInterruptionMode;
} | null = null;
let ambientInterruptionModeRuntime: AmbientInterruptionMode = "stop";
let stopPlaybackFadeInterval: number | null = null;
let stopPlaybackToken = 0;

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

const readGlobalAmbientEnabledSetting = (): boolean =>
  readPreference(GLOBAL_AMBIENT_ENABLED_STORAGE_KEY, false);

const persistGlobalAmbientEnabledSetting = (value: boolean) =>
  persistPreference(
    GLOBAL_AMBIENT_ENABLED_STORAGE_KEY,
    GLOBAL_AMBIENT_ENABLED_EVENT,
    value
  );

const readStoreTrackEnabledSetting = (): boolean =>
  readPreference(STORE_TRACK_ENABLED_STORAGE_KEY, true);

const persistStoreTrackEnabledSetting = (value: boolean) =>
  persistPreference(
    STORE_TRACK_ENABLED_STORAGE_KEY,
    STORE_TRACK_ENABLED_EVENT,
    value
  );

const readAmbientDisableStoreSetting = (): boolean =>
  readPreference(AMBIENT_DISABLE_STORE_STORAGE_KEY, true);

const persistAmbientDisableStoreSetting = (value: boolean) =>
  persistPreference(
    AMBIENT_DISABLE_STORE_STORAGE_KEY,
    AMBIENT_DISABLE_STORE_EVENT,
    value
  );

const parseAmbientInterruptionMode = (
  value: unknown
): AmbientInterruptionMode => {
  if (value === "mute" || value === "pause" || value === "stop") {
    return value;
  }
  return "stop";
};

const parseLaunchStopMode = (value: unknown): LaunchStopMode => {
  if (value === "game_started" || value === "launch_start") {
    return value;
  }
  return "launch_start";
};

const readLaunchStopModeSetting = (): LaunchStopMode => {
  try {
    const raw = window.localStorage?.getItem(LAUNCH_STOP_MODE_STORAGE_KEY);
    const parsed = parseLaunchStopMode(raw);
    launchStopModeRuntime = parsed;
    return parsed;
  } catch (error) {
    console.error("[ThemeDeck] unable to read launch stop mode", error);
    return launchStopModeRuntime;
  }
};

const persistLaunchStopModeSetting = (value: LaunchStopMode) => {
  const normalized = parseLaunchStopMode(value);
  launchStopModeRuntime = normalized;
  try {
    window.localStorage?.setItem(LAUNCH_STOP_MODE_STORAGE_KEY, normalized);
  } catch (error) {
    console.error("[ThemeDeck] unable to store launch stop mode", error);
  }
  window.dispatchEvent(
    new CustomEvent<LaunchStopMode>(LAUNCH_STOP_MODE_EVENT, {
      detail: normalized,
    })
  );
};

const getLaunchStopModeRuntime = (): LaunchStopMode => launchStopModeRuntime;

const readAmbientInterruptionModeSetting = (): AmbientInterruptionMode => {
  try {
    const raw = window.localStorage?.getItem(AMBIENT_INTERRUPTION_MODE_STORAGE_KEY);
    const parsed = parseAmbientInterruptionMode(raw);
    ambientInterruptionModeRuntime = parsed;
    return parsed;
  } catch (error) {
    console.error("[ThemeDeck] unable to read ambient interruption mode", error);
    return ambientInterruptionModeRuntime;
  }
};

const persistAmbientInterruptionModeSetting = (value: AmbientInterruptionMode) => {
  const normalized = parseAmbientInterruptionMode(value);
  ambientInterruptionModeRuntime = normalized;
  try {
    window.localStorage?.setItem(AMBIENT_INTERRUPTION_MODE_STORAGE_KEY, normalized);
  } catch (error) {
    console.error("[ThemeDeck] unable to store ambient interruption mode", error);
  }
  window.dispatchEvent(
    new CustomEvent<AmbientInterruptionMode>(AMBIENT_INTERRUPTION_MODE_EVENT, {
      detail: normalized,
    })
  );
};

const getAmbientInterruptionModeRuntime = (): AmbientInterruptionMode =>
  ambientInterruptionModeRuntime;

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

const clearGlobalAmbientResumeSnapshot = () => {
  globalAmbientResumeSnapshot = null;
};

const captureGlobalAmbientResumeSnapshot = () => {
  const mode = getAmbientInterruptionModeRuntime();
  if (mode === "stop") {
    clearGlobalAmbientResumeSnapshot();
    return;
  }
  if (
    playbackState.appId !== GLOBAL_AMBIENT_APP_ID ||
    playbackState.status !== "playing"
  ) {
    return;
  }
  const audio = sharedAudio;
  const globalTrack = latestGlobalTrackForAutoPlay;
  if (!audio || !globalTrack) {
    return;
  }
  let seconds = 0;
  try {
    if (Number.isFinite(audio.currentTime)) {
      seconds = Math.max(0, audio.currentTime);
    }
  } catch (_ignored) {
    // no-op
  }
  const durationSeconds =
    Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null;
  globalAmbientResumeSnapshot = {
    path: globalTrack.path,
    seconds,
    capturedAtMs: Date.now(),
    durationSeconds,
    mode,
  };
};

const getGlobalAmbientResumeTime = (track: GlobalTrack): number | undefined => {
  const snapshot = globalAmbientResumeSnapshot;
  if (!snapshot) {
    return undefined;
  }
  if (snapshot.path !== track.path) {
    clearGlobalAmbientResumeSnapshot();
    return undefined;
  }
  let nextSeconds = snapshot.seconds;
  if (snapshot.mode === "mute") {
    nextSeconds += Math.max(0, (Date.now() - snapshot.capturedAtMs) / 1000);
  }
  const duration = snapshot.durationSeconds;
  if (duration && Number.isFinite(duration) && duration > 0) {
    nextSeconds %= duration;
  }
  return Math.max(0, nextSeconds);
};

const seekAudioToOffset = async (
  audio: HTMLAudioElement,
  targetSeconds: number
): Promise<boolean> => {
  const resolveTargetTime = () => {
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      return targetSeconds % audio.duration;
    }
    return targetSeconds;
  };

  const tryApply = () => {
    try {
      audio.currentTime = resolveTargetTime();
      return true;
    } catch (_ignored) {
      return false;
    }
  };

  if (tryApply()) {
    return true;
  }

  return await new Promise<boolean>((resolve) => {
    let settled = false;
    let timeoutId = 0;
    const finish = (success: boolean) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      audio.removeEventListener("loadedmetadata", onReady);
      audio.removeEventListener("canplay", onReady);
      audio.removeEventListener("durationchange", onReady);
      audio.removeEventListener("error", onError);
      resolve(success);
    };

    const onReady = () => {
      finish(tryApply());
    };
    const onError = () => {
      finish(false);
    };

    timeoutId = window.setTimeout(() => {
      finish(tryApply());
    }, 1500);

    audio.addEventListener("loadedmetadata", onReady);
    audio.addEventListener("canplay", onReady);
    audio.addEventListener("durationchange", onReady);
    audio.addEventListener("error", onError);
  });
};

const stopPlayback = (fade: boolean) => {
  const token = ++stopPlaybackToken;
  if (stopPlaybackFadeInterval) {
    window.clearInterval(stopPlaybackFadeInterval);
    stopPlaybackFadeInterval = null;
  }
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
    if (token !== stopPlaybackToken) {
      return;
    }
    if (stopPlaybackFadeInterval) {
      window.clearInterval(stopPlaybackFadeInterval);
      stopPlaybackFadeInterval = null;
    }
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
  stopPlaybackFadeInterval = window.setInterval(() => {
    if (token !== stopPlaybackToken) {
      if (stopPlaybackFadeInterval) {
        window.clearInterval(stopPlaybackFadeInterval);
        stopPlaybackFadeInterval = null;
      }
      return;
    }
    step += 1;
    audio.volume = Math.max(0, startingVolume * (1 - step / steps));
    if (step >= steps) {
      if (stopPlaybackFadeInterval) {
        window.clearInterval(stopPlaybackFadeInterval);
        stopPlaybackFadeInterval = null;
      }
      audio.volume = startingVolume;
      finish();
    }
  }, 40);
};

const getPlaySignature = (track: GameTrack, reason: PlaybackReason): string =>
  `${reason}|${track.appId}|${track.path}`;

const isIgnorablePlaybackError = (error: unknown): boolean => {
  if (error instanceof DOMException) {
    if (error.name === "AbortError" || error.name === "NotAllowedError") {
      return true;
    }
  }
  const message = String(
    (error as { message?: unknown })?.message ?? error ?? ""
  ).toLowerCase();
  return (
    message.includes("interrupted") ||
    message.includes("abort") ||
    message.includes("notallowederror")
  );
};

const playTrack = async (track: GameTrack, reason: PlaybackReason) => {
  stopPlaybackToken += 1;
  if (stopPlaybackFadeInterval) {
    window.clearInterval(stopPlaybackFadeInterval);
    stopPlaybackFadeInterval = null;
  }
  const inDesktopMode = await refreshDesktopModeState();
  if (inDesktopMode) {
    return;
  }
  if (runningGameAppId !== null) {
    return;
  }

  const signature = getPlaySignature(track, reason);
  if (playInFlightSignature === signature) {
    return;
  }
  const invocationId = ++playInvocationCounter;
  playInFlightSignature = signature;
  const audio = ensureAudio();

  try {
    const nextUrl = await resolveAudioUrl(track);
    if (invocationId !== playInvocationCounter) {
      return;
    }
    if (runningGameAppId !== null) {
      return;
    }
    const sameTrack =
      playbackState.appId === track.appId &&
      audio.src === nextUrl &&
      playbackState.status === "playing";

    if (!sameTrack) {
      audio.src = nextUrl;
    }

    audio.volume = clamp(track.volume ?? 1);
    const configuredOffset = clamp(track.startOffset ?? 0, 0, 30);
    const offset =
      typeof track.resumeTime === "number" && Number.isFinite(track.resumeTime)
        ? Math.max(0, track.resumeTime)
        : configuredOffset;
    let seekApplied = true;
    if (offset > 0) {
      seekApplied = await seekAudioToOffset(audio, offset);
    } else if (!sameTrack) {
      try {
        audio.currentTime = 0;
      } catch (_ignored) {
        // no-op
      }
    }
    if (runningGameAppId !== null) {
      return;
    }
    await audio.play();
    if (offset > 0 && !seekApplied) {
      await seekAudioToOffset(audio, offset);
    }
    if (invocationId !== playInvocationCounter) {
      return;
    }
    if (
      reason === "auto" &&
      track.appId === GLOBAL_AMBIENT_APP_ID &&
      typeof track.resumeTime === "number"
    ) {
      clearGlobalAmbientResumeSnapshot();
    }
    notifyPlayback({ appId: track.appId, reason, status: "playing" });
  } catch (error) {
    if (invocationId !== playInvocationCounter) {
      return;
    }
    if (isIgnorablePlaybackError(error)) {
      console.warn("[ThemeDeck] playback interrupted", error);
      return;
    }
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
  } finally {
    if (
      invocationId === playInvocationCounter &&
      playInFlightSignature === signature
    ) {
      playInFlightSignature = null;
    }
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

const applyStartOffsetToActiveTrack = (appId: number, startOffset: number) => {
  if (!sharedAudio) {
    return;
  }
  if (playbackState.appId !== appId || playbackState.status !== "playing") {
    return;
  }
  try {
    sharedAudio.currentTime = clamp(startOffset, 0, 30);
  } catch (_ignored) {
    // no-op
  }
};

const notifyFocus = (appId: number | null) => {
  focusedAppId = appId;
  focusListeners.forEach((listener) => listener(appId));
  scheduleAutoPlaybackFromContext();
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
    const pathname = getLibraryPath();
    if (!pathname) {
      // Steam can briefly report an empty path during focus transitions; do not
      // clear focus state on that transient signal.
      return;
    }
    const appId = readAppIdFromLocation();
    // Only promote a resolved app id. Do not push null from this poller, because
    // transient route states can otherwise interrupt active game playback.
    if (appId && appId !== focusedAppId) {
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

const parseUIMode = (value: unknown): number | null => {
  if (typeof value === "number" && !Number.isNaN(value)) {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (normalized === "desktop") {
      return UI_MODE_DESKTOP;
    }
    if (normalized === "gamepad") {
      return UI_MODE_GAMEPAD;
    }
    const parsed = Number.parseInt(normalized, 10);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
    return null;
  }
  if (value && typeof value === "object") {
    const candidate =
      (value as any).m_eUIMode ??
      (value as any).eUIMode ??
      (value as any).uiMode ??
      (value as any).mode;
    return parseUIMode(candidate);
  }
  return null;
};

const setDesktopModeState = (next: boolean) => {
  if (next === desktopModeActive) {
    return;
  }
  desktopModeActive = next;
  if (desktopModeActive && playbackState.status === "playing") {
    stopPlayback(true);
  }
  scheduleAutoPlaybackFromContext();
};

const readDesktopModeFromWindows = async (): Promise<boolean | null> => {
  try {
    const ui = (window as any)?.SteamClient?.UI;
    const getDesired = ui?.GetDesiredSteamUIWindows;
    if (typeof getDesired !== "function") {
      return null;
    }
    const windows = await getDesired.call(ui);
    if (!Array.isArray(windows) || !windows.length) {
      return null;
    }
    const hasGamepadWindow = windows.some((entry) => {
      const type = Number((entry as any)?.windowType);
      return type === 0 || type === 1;
    });
    const hasDesktopWindow = windows.some((entry) => {
      const type = Number((entry as any)?.windowType);
      return type === 5 || type === 6 || type === 7;
    });
    if (hasGamepadWindow) {
      return false;
    }
    if (hasDesktopWindow) {
      return true;
    }
  } catch (error) {
    console.error("[ThemeDeck] ui window probe failed", error);
  }
  return null;
};

const refreshDesktopModeState = async (force = false): Promise<boolean> => {
  const now = Date.now();
  if (!force && now - desktopModeLastCheck < UI_MODE_CACHE_MS) {
    return desktopModeActive;
  }
  if (desktopModeRefreshInFlight) {
    return desktopModeRefreshInFlight;
  }

  desktopModeRefreshInFlight = (async () => {
    let resolved: boolean | null = null;
    try {
      const ui = (window as any)?.SteamClient?.UI;
      const getMode = ui?.GetUIMode;
      if (typeof getMode === "function") {
        const modeValue = await getMode.call(ui);
        const mode = parseUIMode(modeValue);
        if (mode !== null) {
          resolved = mode === UI_MODE_DESKTOP;
        }
      }
    } catch (error) {
      console.error("[ThemeDeck] ui mode probe failed", error);
    }

    if (resolved === null) {
      resolved = await readDesktopModeFromWindows();
    }

    if (resolved !== null) {
      setDesktopModeState(resolved);
    }
    desktopModeLastCheck = Date.now();
    return desktopModeActive;
  })();

  try {
    return await desktopModeRefreshInFlight;
  } finally {
    desktopModeRefreshInFlight = null;
  }
};

const startDesktopModeWatcher = () => {
  void refreshDesktopModeState(true);
  if (uiModePollInterval) {
    return;
  }

  const ui = (window as any)?.SteamClient?.UI;
  const registerForUIModeChanged = ui?.RegisterForUIModeChanged;
  if (typeof registerForUIModeChanged === "function") {
    try {
      const token = registerForUIModeChanged.call(ui, (modeValue: unknown) => {
        const parsed = parseUIMode(modeValue);
        if (parsed !== null) {
          setDesktopModeState(parsed === UI_MODE_DESKTOP);
          return;
        }
        void refreshDesktopModeState(true);
      });
      stopUIModeSubscription = wrapUnsubscribe(token);
    } catch (error) {
      console.error("[ThemeDeck] ui mode subscription failed", error);
    }
  }

  uiModePollInterval = window.setInterval(() => {
    void refreshDesktopModeState();
  }, UI_MODE_POLL_MS);
};

const stopDesktopModeWatcher = () => {
  stopUIModeSubscription?.();
  stopUIModeSubscription = null;
  if (uiModePollInterval) {
    window.clearInterval(uiModePollInterval);
    uiModePollInterval = null;
  }
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

const isEligibleRunningAppId = (appId: number): boolean =>
  Number.isFinite(appId) &&
  appId > 0 &&
  !LIBRARY_EXCLUDED_APP_IDS.has(appId);

const getStateText = (candidate: any): string =>
  String(
    candidate?.state ??
      candidate?.app_state ??
      candidate?.strAppState ??
      candidate?.status ??
      candidate?.m_eAppState ??
      candidate?.eAppState ??
      ""
  )
    .trim()
    .toLowerCase();

const hasStartedMarker = (candidate: any): boolean => {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }
  const startedFlags = [
    candidate.playing,
    candidate.in_game,
    candidate.inGame,
    candidate.bInGame,
    candidate.BInGame,
    candidate.is_ingame,
    candidate.isInGame,
  ];
  if (
    startedFlags.some(
      (value) =>
        value === true ||
        value === 1 ||
        value === "1" ||
        String(value).toLowerCase() === "true"
    )
  ) {
    return true;
  }
  const stateText = getStateText(candidate);
  if (!stateText) {
    return false;
  }
  if (
    stateText.includes("in-game") ||
    stateText.includes("in_game") ||
    stateText.includes("ingame") ||
    stateText.includes("playing") ||
    stateText.includes("active") ||
    stateText === "running"
  ) {
    return true;
  }
  return false;
};

const hasLaunchingMarker = (candidate: any): boolean => {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }
  const launchFlags = [
    candidate.running,
    candidate.is_running,
    candidate.isRunning,
    candidate.bIsRunning,
    candidate.BIsRunning,
  ];
  if (
    launchFlags.some(
      (value) =>
        value === true ||
        value === 1 ||
        value === "1" ||
        String(value).toLowerCase() === "true"
    )
  ) {
    return true;
  }
  const stateText = getStateText(candidate);
  if (!stateText) {
    return false;
  }
  return (
    stateText.includes("launch") ||
    stateText.includes("starting") ||
    stateText.includes("prelaunch") ||
    stateText.includes("pre-launch") ||
    stateText.includes("queued") ||
    stateText.includes("initializing")
  );
};

type RunningAppSnapshot = {
  started: Set<number>;
  launching: Set<number>;
};

const collectRunningAppStates = (
  candidate: any,
  target: RunningAppSnapshot,
  assumeRunning: boolean,
  visited = new Set<any>()
) => {
  if (candidate == null) {
    return;
  }

  if (typeof candidate === "number" || typeof candidate === "bigint") {
    const appId = Number(candidate);
    if (assumeRunning && isEligibleRunningAppId(appId)) {
      target.launching.add(appId);
    }
    return;
  }

  if (typeof candidate === "string") {
    const parsed = Number.parseInt(candidate, 10);
    if (assumeRunning && !Number.isNaN(parsed) && isEligibleRunningAppId(parsed)) {
      target.launching.add(parsed);
    }
    return;
  }

  if (typeof candidate !== "object") {
    return;
  }

  if (visited.has(candidate)) {
    return;
  }
  visited.add(candidate);

  if (Array.isArray(candidate)) {
    candidate.forEach((entry) =>
      collectRunningAppStates(entry, target, assumeRunning, visited)
    );
    return;
  }
  if (candidate instanceof Set) {
    candidate.forEach((entry) =>
      collectRunningAppStates(entry, target, assumeRunning, visited)
    );
    return;
  }
  if (candidate instanceof Map) {
    candidate.forEach((value, key) => {
      collectRunningAppStates(value, target, assumeRunning, visited);
      if (assumeRunning) {
        collectRunningAppStates(key, target, true, visited);
      }
    });
    return;
  }

  const appId = extractAppId(candidate);
  const started = hasStartedMarker(candidate);
  const launching = hasLaunchingMarker(candidate);
  if (appId && (assumeRunning || started || launching)) {
    if (isEligibleRunningAppId(appId)) {
      if (started) {
        target.started.add(appId);
      } else {
        target.launching.add(appId);
      }
    }
  }

  [
    "runningApps",
    "running_apps",
    "apps",
    "sessions",
    "games",
    "rgRunningApps",
    "rgApps",
    "rgGames",
    "map_running",
  ].forEach((key) => {
    if (key in candidate) {
      collectRunningAppStates(candidate[key], target, assumeRunning, visited);
    }
  });
};

const readRunningGameAppId = async (): Promise<number | null> => {
  const snapshot: RunningAppSnapshot = {
    started: new Set<number>(),
    launching: new Set<number>(),
  };
  const steamApps = (window as any)?.SteamClient?.Apps;
  const appStore = (window as any)?.appStore;

  const methodSources: Array<{ owner: any; method: string; assumeRunning: boolean }> = [
    { owner: steamApps, method: "GetRunningApps", assumeRunning: true },
    { owner: steamApps, method: "GetRunningAppList", assumeRunning: true },
    { owner: steamApps, method: "GetAppsRunning", assumeRunning: true },
    { owner: steamApps, method: "GetCurrentlyRunningApp", assumeRunning: true },
    { owner: appStore, method: "GetRunningApps", assumeRunning: true },
    { owner: appStore, method: "GetCurrentlyRunningApp", assumeRunning: true },
  ];

  for (const source of methodSources) {
    const fn = source.owner?.[source.method];
    if (typeof fn !== "function") {
      continue;
    }
    try {
      const result = await Promise.resolve(fn.call(source.owner));
      collectRunningAppStates(result, snapshot, source.assumeRunning);
    } catch (_ignored) {
      // no-op
    }
  }

  [
    steamApps?.m_mapRunningApps,
    steamApps?.m_runningApps,
    steamApps?.runningApps,
    appStore?.m_mapRunningApps,
    appStore?.m_runningApps,
    appStore?.runningApps,
    (Router as any)?.WindowStore?.m_mapRunningApps,
    (Router as any)?.WindowStore?.m_runningApps,
    (Router as any)?.WindowStore?.runningApps,
    (Router as any)?.MainRunningApp,
    (Router as any)?.RunningApp,
  ].forEach((value) => collectRunningAppStates(value, snapshot, true));

  const mode = getLaunchStopModeRuntime();
  const ids =
    mode === "game_started"
      ? snapshot.started
      : new Set<number>([...snapshot.started, ...snapshot.launching]);

  const routeAppId = readAppIdFromLocation();
  if (routeAppId && ids.has(routeAppId)) {
    return routeAppId;
  }
  if (focusedAppId && ids.has(focusedAppId)) {
    return focusedAppId;
  }
  const ordered = Array.from(ids.values()).sort((a, b) => a - b);
  return ordered[0] ?? null;
};

const setRunningGameAppId = (next: number | null) => {
  const normalized = next && isEligibleRunningAppId(next) ? next : null;
  if (runningGameAppId === normalized) {
    return;
  }
  runningGameAppId = normalized;
  if (runningGameAppId !== null && playbackState.status === "playing") {
    if (playbackState.appId === GLOBAL_AMBIENT_APP_ID) {
      captureGlobalAmbientResumeSnapshot();
    }
    stopPlayback(true);
  }
  scheduleAutoPlaybackFromContext();
};

const refreshRunningGameState = async () => {
  if (runningAppRefreshInFlight) {
    return;
  }
  runningAppRefreshInFlight = true;
  try {
    const next = await readRunningGameAppId();
    setRunningGameAppId(next);
  } catch (error) {
    console.error("[ThemeDeck] running game probe failed", error);
  } finally {
    runningAppRefreshInFlight = false;
  }
};

const startRunningGameWatcher = () => {
  if (runningAppPollInterval) {
    return;
  }

  const apps = (window as any)?.SteamClient?.Apps;
  if (!apps) {
    if (!runningAppRetry) {
      runningAppRetry = window.setInterval(() => {
        const retryApps = (window as any)?.SteamClient?.Apps;
        if (!retryApps) {
          return;
        }
        window.clearInterval(runningAppRetry!);
        runningAppRetry = null;
        startRunningGameWatcher();
      }, 2000);
    }
    return;
  }

  const registerMethods = [
    "RegisterForRunningAppsChanged",
    "RegisterForRunningAppChanges",
    "RegisterForAppRunningStateChanged",
    "RegisterForAppRunningStateChange",
    "RegisterForGameActionStart",
    "RegisterForGameActionEnd",
    "RegisterForGameLaunched",
    "RegisterForGameExited",
    "RegisterForAppDetails",
    "RegisterForAppOverviewChanges",
  ];

  registerMethods.forEach((method) => {
    const register = apps?.[method];
    if (typeof register !== "function") {
      return;
    }
    try {
      const token = register.call(apps, () => {
        void refreshRunningGameState();
      });
      const clean = wrapUnsubscribe(token);
      if (clean) {
        runningAppSubscriptions.push(clean);
      }
    } catch (error) {
      console.error("[ThemeDeck] running watcher failed", { method, error });
    }
  });

  runningAppPollInterval = window.setInterval(() => {
    void refreshRunningGameState();
  }, RUNNING_APP_POLL_MS);
  void refreshRunningGameState();
};

const stopRunningGameWatcher = () => {
  runningAppSubscriptions.splice(0).forEach((clean) => {
    try {
      clean();
    } catch (error) {
      console.error("[ThemeDeck] running watcher cleanup failed", error);
    }
  });
  if (runningAppPollInterval) {
    window.clearInterval(runningAppPollInterval);
    runningAppPollInterval = null;
  }
  if (runningAppRetry) {
    window.clearInterval(runningAppRetry);
    runningAppRetry = null;
  }
  runningAppRefreshInFlight = false;
  runningGameAppId = null;
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

const coerceMenuChildren = (children: any): any[] | null => {
  if (!children) return null;
  if (Array.isArray(children)) return children;
  if (Array.isArray(children?.props?.children)) return children.props.children;
  if (Array.isArray(children?.children)) return children.children;
  return null;
};

const pruneThemeDeckMenu = (children: any) => {
  const list = coerceMenuChildren(children);
  if (!Array.isArray(list)) return;
  const existing = list.findIndex(
    (entry) => entry?.key === "themedeck-change-music"
  );
  if (existing !== -1) {
    list.splice(existing, 1);
  }
};

const insertThemeDeckMenu = (children: any, appId: number) => {
  if (!appId) return;
  const list = coerceMenuChildren(children);
  if (!Array.isArray(list)) return;

  pruneThemeDeckMenu(list);

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
        const latestAppId =
          extractAppId(appId) ??
          readAppIdFromLocation() ??
          extractAppId(focusedAppId);
        if (!latestAppId) {
          toaster.toast({
            title: "ThemeDeck",
            body: "Couldn't determine current game app id",
          });
          return;
        }
        Navigation.CloseSideMenus?.();
        Navigation.Navigate(`/themedeck/${latestAppId}`);
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

const isGameContextMenu = (items: any[]): boolean => {
  if (!items?.length) return false;
  return !!findInReactTree(
    items,
    (node: any) =>
      typeof node?.props?.onSelected === "function" &&
      node.props.onSelected.toString().includes("launchSource")
  );
};

const isLibraryAppContextMenu = (items: any[]): boolean => {
  if (!items?.length) return false;
  return !!findInReactTree(items, (node: any) => {
    if (typeof node?.props?.onSelected !== "function") return false;
    const source = node.props.onSelected.toString();
    return (
      source.includes("launchSource") ||
      source.includes("AppProperties") ||
      source.includes("ShowAppProperties") ||
      source.includes("InstallApp") ||
      source.includes("Download")
    );
  });
};

const deriveAppIdFromMenuItems = (
  items: any[] | null,
  fallback: number | null
): number | null => {
  if (!items || !items.length) {
    return fallback ?? null;
  }
  const parent = items.find((entry) => entry?._owner?.pendingProps?.overview?.appid);
  const fromOwner = extractAppId(parent?._owner?.pendingProps?.overview?.appid);
  if (fromOwner) {
    return fromOwner;
  }

  const fromOverview = findInTree(
    items,
    (node) => node?.overview?.appid ?? node?.props?.overview?.appid,
    { walkable: ["props", "children", "_owner", "pendingProps"] }
  );
  const overviewAppId = extractAppId(
    fromOverview?.overview?.appid,
    fromOverview?.props?.overview?.appid
  );
  if (overviewAppId) {
    return overviewAppId;
  }

  const foundAppNode = findInTree(
    items,
    (node) =>
      node?.app?.appid ??
      node?.props?.app?.appid ??
      node?.appid ??
      node?.props?.appid ??
      node?.app_id ??
      node?.props?.app_id,
    { walkable: ["props", "children", "_owner", "pendingProps"] }
  );
  const fromAppNode = extractAppId(
    foundAppNode?.app?.appid,
    foundAppNode?.props?.app?.appid,
    foundAppNode?.appid,
    foundAppNode?.props?.appid,
    foundAppNode?.app_id,
    foundAppNode?.props?.app_id
  );
  if (fromAppNode) {
    return fromAppNode;
  }

  return fallback ?? null;
};

const patchMenuItems = (
  menuItems: any,
  fallbackAppId: number | null
): number | null => {
  const entries = coerceMenuChildren(menuItems);
  if (!Array.isArray(entries) || !entries.length) return null;
  if (!isGameContextMenu(entries) && !isLibraryAppContextMenu(entries)) {
    return null;
  }
  const derivedAppId = deriveAppIdFromMenuItems(entries, fallbackAppId);
  if (!derivedAppId) return null;
  insertThemeDeckMenu(entries, derivedAppId);
  return derivedAppId;
};

const patchContextMenuFocus = () => {
  const MenuComponent = resolveLibraryContextMenu();
  if (!MenuComponent?.prototype) {
    return null;
  }

  const state: { appId: number | null } = { appId: null };

  const patches: {
    outer?: Patch;
    inner?: Patch;
  } = {};

  patches.outer = afterPatch(
    MenuComponent.prototype,
    "render",
    (_args: Record<string, unknown>[], component: any) => {
      let appId =
        extractAppId(component?._owner?.pendingProps?.overview?.appid) ?? null;
      if (!appId) {
        const fallback = findInTree(
          component?.props?.children,
          (node) => node?.app?.appid,
          { walkable: ["props", "children"] }
        );
        if (fallback?.app?.appid) {
          appId = extractAppId(fallback.app.appid);
        }
      }
      if (appId) {
        state.appId = appId;
        notifyFocus(appId);
      }

      if (!patches.inner) {
        patches.inner = afterPatch(
          component,
          "type",
          (_innerArgs: Record<string, unknown>[], rendered: any) => {
            afterPatch(
              rendered.type.prototype,
              "render",
              (_renderArgs: Record<string, unknown>[], node: any) => {
                const menuItems =
                  node?.props?.children?.[0] ?? node?.props?.children;
                const fallbackAppId =
                  extractAppIdFromTree(node) ?? state.appId;
                const patched = patchMenuItems(menuItems, fallbackAppId);
                if (patched) {
                  state.appId = patched;
                  notifyFocus(patched);
                }
                return node;
              }
            );
            afterPatch(
              rendered.type.prototype,
              "shouldComponentUpdate",
              ([nextProps]: any, shouldUpdate: any) => {
                if (shouldUpdate === true) {
                  const fallbackAppId =
                    extractAppIdFromTree(nextProps?.children) ?? state.appId;
                  const patched = patchMenuItems(
                    nextProps?.children,
                    fallbackAppId
                  );
                  if (patched) {
                    state.appId = patched;
                    notifyFocus(patched);
                  }
                }
                return shouldUpdate;
              }
            );
            return rendered;
          }
        );
      } else if (appId) {
        const patched = patchMenuItems(component?.props?.children, appId);
        if (patched) {
          state.appId = patched;
          notifyFocus(patched);
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

  useEffect(() => {
    notifyFocus(appId);
    return () => {
      // Route transitions can briefly unmount/remount detail pages; avoid pushing
      // transient null focus that can cause ambient restart jitter.
      window.setTimeout(() => {
        if (readAppIdFromLocation() === null) {
          notifyFocus(null);
        }
      }, 120);
    };
  }, [appId]);

  return null;
};

const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value));

const getErrorMessage = (error: unknown, fallback: string) => {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  if (error && typeof error === "object") {
    const candidate = error as Record<string, unknown>;
    const nested =
      candidate.message ??
      candidate.error ??
      (candidate.cause as Record<string, unknown> | undefined)?.message ??
      (candidate.details as Record<string, unknown> | undefined)?.message;
    if (typeof nested === "string" && nested.trim()) {
      return nested;
    }
    try {
      const serialized = JSON.stringify(error);
      if (serialized && serialized !== "{}") {
        return serialized;
      }
    } catch (_ignored) {
      // no-op
    }
  }
  return fallback;
};

const formatDuration = (seconds?: number | null) => {
  if (!seconds || seconds <= 0) {
    return "";
  }
  const total = Math.floor(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const normalizeGlobalTrack = (
  raw: BackendTrack | null | undefined
): GlobalTrack | null => {
  if (!raw?.path) {
    return null;
  }
  return {
    path: raw.path,
    filename: raw.filename || raw.path.split("/").pop() || "Global track",
    volume: typeof raw.volume === "number" ? clamp(raw.volume) : 1,
    startOffset:
      typeof raw.start_offset === "number"
        ? clamp(raw.start_offset, 0, 30)
        : 0,
  };
};

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
      startOffset:
        typeof track.start_offset === "number"
          ? clamp(track.start_offset, 0, 30)
          : 0,
    };
  }

  return normalized;
};

const getStoreRouteCandidates = (): string[] => {
  const candidates = new Set<string>();
  const pushLocation = (loc?: Location | null) => {
    if (!loc) return;
    const composed = `${loc.pathname || ""}${loc.hash || ""}${loc.search || ""}`
      .trim()
      .toLowerCase();
    if (composed) {
      candidates.add(composed);
    }
    const href = String(loc.href || "").trim().toLowerCase();
    if (href) {
      candidates.add(href);
    }
  };

  try {
    const focusedWindow =
      window.SteamUIStore?.GetFocusedWindowInstance?.() ??
      Router.WindowStore?.GamepadUIMainWindowInstance;
    const browserWindow =
      focusedWindow?.BrowserWindow ??
      Router.WindowStore?.GamepadUIMainWindowInstance?.BrowserWindow;
    pushLocation(browserWindow?.location ?? null);
  } catch {
    // ignore
  }

  pushLocation(window.location);
  try {
    pushLocation(window.top?.location ?? null);
  } catch {
    // ignore cross-origin access
  }

  return Array.from(candidates);
};

const looksLikeStoreSignal = (value: unknown): boolean => {
  if (typeof value !== "string") return false;
  const text = value.toLowerCase();
  return (
    text.includes("/store") ||
    text.includes("#/store") ||
    text.includes("tab=store") ||
    text.includes("storehome") ||
    text.includes("store.steampowered.com") ||
    text.includes("store%2esteampowered%2ecom") ||
    (text.includes("openurl") && text.includes("store"))
  );
};

const looksLikeThemeDeckSignal = (value: unknown): boolean => {
  if (typeof value !== "string") return false;
  const text = value.toLowerCase();
  return (
    text.includes("/themedeck") ||
    text.includes("#/themedeck") ||
    text.includes("%2fthemedeck")
  );
};

const isStoreRoute = (route: string): boolean => {
  const text = (route || "").toLowerCase();
  if (!text) return false;
  const variants = new Set<string>([text]);
  const tryDecode = (value: string) => {
    try {
      const decoded = decodeURIComponent(value);
      if (decoded && decoded !== value) {
        variants.add(decoded);
      }
    } catch {
      // ignore decode issues
    }
  };
  tryDecode(text);
  for (const value of Array.from(variants)) {
    tryDecode(value);
  }
  for (const value of variants) {
    if (looksLikeStoreSignal(value)) {
      return true;
    }
  }
  return false;
};

const detectStoreFromWindowState = (): boolean => {
  const focusedCandidates = [
    (window as any).SteamUIStore?.GetFocusedWindowInstance?.(),
    (Router as any)?.WindowStore?.GetFocusedWindowInstance?.(),
    (Router as any)?.WindowStore?.m_FocusedWindowInstance,
    (Router as any)?.WindowStore?.m_FocusedWindow,
    (Router as any)?.WindowStore,
    (window as any).SteamUIStore,
  ];
  for (const candidate of focusedCandidates) {
    if (!candidate) continue;
    const directValues = [
      candidate?.strTitle,
      candidate?.m_strTitle,
      candidate?.title,
      candidate?.name,
      candidate?.WindowType,
      candidate?.m_eWindowType,
      candidate?.route,
      candidate?.path,
      candidate?.url,
      candidate?.href,
      candidate?.location?.href,
      candidate?.BrowserWindow?.location?.href,
      candidate?.BrowserWindow?.document?.URL,
      candidate?.BrowserWindow?.document?.location?.href,
    ];
    if (directValues.some((value) => looksLikeStoreSignal(value))) {
      return true;
    }
    const queue: unknown[] = [candidate];
    const seen = new WeakSet<object>();
    let scanned = 0;
    while (queue.length && scanned < 250) {
      const next = queue.shift();
      scanned += 1;
      if (!next || typeof next !== "object") {
        continue;
      }
      const objectValue = next as Record<string, unknown>;
      if (seen.has(objectValue)) {
        continue;
      }
      seen.add(objectValue);
      for (const [key, value] of Object.entries(objectValue)) {
        if (
          typeof value === "string" &&
          /url|href|path|route|uri|src|title|name|location/i.test(key) &&
          looksLikeStoreSignal(value)
        ) {
          return true;
        }
        if (value && typeof value === "object") {
          queue.push(value);
        }
      }
    }
  }
  return false;
};

const isThemeDeckRouteActive = (): boolean => {
  const candidates = getStoreRouteCandidates();
  if (candidates.some((route) => looksLikeThemeDeckSignal(route))) {
    return true;
  }
  try {
    const path = getLibraryPath();
    if (looksLikeThemeDeckSignal(path)) {
      return true;
    }
  } catch {
    // ignore
  }
  return false;
};

const isStorePathSync = (): boolean => {
  if (getStoreRouteCandidates().some((route) => isStoreRoute(route))) {
    return true;
  }
  if (detectStoreFromWindowState()) {
    return true;
  }
  try {
    const hasStoreFrame =
      document.querySelector(
        "iframe[src*='store.steampowered.com'], webview[src*='store.steampowered.com'], a[href*='store.steampowered.com']"
      ) !== null;
    if (hasStoreFrame) {
      return true;
    }
  } catch {
    // ignore DOM probe failures
  }
  return false;
};

const isStorePath = (): boolean => storeContextActive || isStorePathSync();

const detectStoreFromTabs = async (): Promise<boolean> => {
  const probeCode = `
    (() => {
      try {
        const href = String(window.location?.href || "").toLowerCase();
        const path = String(window.location?.pathname || "").toLowerCase();
        const hash = String(window.location?.hash || "").toLowerCase();
        const search = String(window.location?.search || "").toLowerCase();
        const full = href + " " + path + " " + hash + " " + search;
        if (full.includes("store.steampowered.com") || full.includes("/store") || full.includes("#/store")) {
          return true;
        }
        const hasStoreFrame = !!document.querySelector("iframe[src*='store.steampowered.com'], webview[src*='store.steampowered.com'], a[href*='store.steampowered.com']");
        if (hasStoreFrame) {
          return true;
        }
        return false;
      } catch {
        return false;
      }
    })();
  `;
  const results = await Promise.all(
    SP_TAB_CANDIDATES.map(async (tab) => {
      try {
        const result = await Promise.race([
          executeInTab(tab, true, probeCode),
          new Promise<null>((resolve) => {
            window.setTimeout(() => resolve(null), 1000);
          }),
        ]);
        const value =
          result && typeof result === "object" && "result" in result
            ? (result as { result?: unknown }).result
            : result;
        return value === true || value === "true";
      } catch {
        return false;
      }
    })
  );
  return results.some(Boolean);
};

const refreshStoreContext = async () => {
  if (autoPlaybackStoreProbeInFlight) {
    return;
  }
  autoPlaybackStoreProbeInFlight = true;
  try {
    const syncStore = isStorePathSync();
    const tabStore = await detectStoreFromTabs();
    const next = syncStore || tabStore;
    if (next !== storeContextActive) {
      storeContextActive = next;
      scheduleAutoPlaybackFromContext();
    }
  } catch (error) {
    console.error("[ThemeDeck] refresh store context failed", error);
  } finally {
    autoPlaybackStoreProbeInFlight = false;
  }
};

const resolveAutoTrackFromContext = (): GameTrack | null => {
  if (runningGameAppId !== null) {
    return null;
  }

  const routeAppId = readAppIdFromLocation();
  const effectiveAppId = routeAppId ?? focusedAppId;

  if (effectiveAppId && readAutoPlaySetting()) {
    const gameTrack = latestTracksForAutoPlay[effectiveAppId];
    if (gameTrack) {
      return gameTrack;
    }
  }

  if (effectiveAppId) {
    return null;
  }

  const inStore = isStorePath();
  if (inStore && readStoreTrackEnabledSetting() && latestStoreTrackForAutoPlay) {
    return {
      appId: STORE_TRACK_APP_ID,
      path: latestStoreTrackForAutoPlay.path,
      filename: latestStoreTrackForAutoPlay.filename,
      volume: latestStoreTrackForAutoPlay.volume,
      startOffset: latestStoreTrackForAutoPlay.startOffset,
    };
  }
  if (inStore && readAmbientDisableStoreSetting()) {
    return null;
  }

  if (!readGlobalAmbientEnabledSetting()) {
    return null;
  }

  if (!latestGlobalTrackForAutoPlay) {
    return null;
  }

  const currentPath = getLibraryPath();
  if (!currentPath && playbackState.reason === "auto" && playbackState.status === "playing") {
    if (
      playbackState.appId === STORE_TRACK_APP_ID &&
      readStoreTrackEnabledSetting() &&
      latestStoreTrackForAutoPlay
    ) {
      return {
        appId: STORE_TRACK_APP_ID,
        path: latestStoreTrackForAutoPlay.path,
        filename: latestStoreTrackForAutoPlay.filename,
        volume: latestStoreTrackForAutoPlay.volume,
        startOffset: latestStoreTrackForAutoPlay.startOffset,
      };
    }
    if (playbackState.appId === GLOBAL_AMBIENT_APP_ID && latestGlobalTrackForAutoPlay) {
      const resumeTime = getGlobalAmbientResumeTime(latestGlobalTrackForAutoPlay);
      return {
        appId: GLOBAL_AMBIENT_APP_ID,
        path: latestGlobalTrackForAutoPlay.path,
        filename: latestGlobalTrackForAutoPlay.filename,
        volume: latestGlobalTrackForAutoPlay.volume,
        startOffset: latestGlobalTrackForAutoPlay.startOffset,
        resumeTime,
      };
    }
    if (playbackState.appId && playbackState.appId > 0) {
      const currentGameTrack = latestTracksForAutoPlay[playbackState.appId];
      if (currentGameTrack) {
        return currentGameTrack;
      }
    }
  }

  if (readAmbientDisableStoreSetting() && isStorePath()) {
    return null;
  }

  const resumeTime = getGlobalAmbientResumeTime(latestGlobalTrackForAutoPlay);
  return {
    appId: GLOBAL_AMBIENT_APP_ID,
    path: latestGlobalTrackForAutoPlay.path,
    filename: latestGlobalTrackForAutoPlay.filename,
    volume: latestGlobalTrackForAutoPlay.volume,
    startOffset: latestGlobalTrackForAutoPlay.startOffset,
    resumeTime,
  };
};

const applyAutoPlaybackFromContext = () => {
  if (desktopModeActive) {
    if (playbackState.status === "playing") {
      stopPlayback(true);
    }
    return;
  }

  if (runningGameAppId !== null) {
    if (playbackState.status === "playing") {
      if (playbackState.appId === GLOBAL_AMBIENT_APP_ID) {
        captureGlobalAmbientResumeSnapshot();
      }
      stopPlayback(true);
    }
    return;
  }

  if (isThemeDeckRouteActive()) {
    if (playbackState.reason === "auto" && playbackState.status === "playing") {
      if (playbackState.appId === GLOBAL_AMBIENT_APP_ID) {
        captureGlobalAmbientResumeSnapshot();
      }
      stopPlayback(true);
    }
    return;
  }

  const shouldSuppressGlobal =
    !readGlobalAmbientEnabledSetting() ||
    (readAmbientDisableStoreSetting() && isStorePath());
  if (
    shouldSuppressGlobal &&
    playbackState.appId === GLOBAL_AMBIENT_APP_ID &&
    playbackState.status === "playing"
  ) {
    captureGlobalAmbientResumeSnapshot();
    stopPlayback(true);
    return;
  }
  if (playbackState.reason === "manual") {
    return;
  }

  const nextTrack = resolveAutoTrackFromContext();
  if (!nextTrack) {
    if (playbackState.reason === "auto" && playbackState.status === "playing") {
      if (playbackState.appId === GLOBAL_AMBIENT_APP_ID) {
        captureGlobalAmbientResumeSnapshot();
      }
      stopPlayback(true);
    }
    return;
  }

  if (
    playbackState.reason === "auto" &&
    playbackState.status === "playing" &&
    playbackState.appId === GLOBAL_AMBIENT_APP_ID &&
    nextTrack.appId !== GLOBAL_AMBIENT_APP_ID
  ) {
    captureGlobalAmbientResumeSnapshot();
  }

  if (
    playbackState.reason === "auto" &&
    playbackState.status === "playing" &&
    playbackState.appId === nextTrack.appId
  ) {
    return;
  }
  playTrack(nextTrack, "auto");
};

const scheduleAutoPlaybackFromContext = () => {
  if (autoPlaybackTick) {
    window.clearTimeout(autoPlaybackTick);
  }
  autoPlaybackTick = window.setTimeout(() => {
    autoPlaybackTick = null;
    applyAutoPlaybackFromContext();
  }, 0);
};

const refreshAutoPlaybackTrackCache = async () => {
  if (autoPlaybackTrackRefreshInFlight) {
    return;
  }
  autoPlaybackTrackRefreshInFlight = true;
  try {
    const [trackData, globalData, storeData] = await Promise.all([
      fetchTracks(),
      fetchGlobalTrack(),
      fetchStoreTrack(),
    ]);
    latestTracksForAutoPlay = normalizeTracks(trackData);
    latestGlobalTrackForAutoPlay = normalizeGlobalTrack(globalData);
    latestStoreTrackForAutoPlay = normalizeGlobalTrack(storeData);
    if (
      !latestGlobalTrackForAutoPlay ||
      (globalAmbientResumeSnapshot &&
        globalAmbientResumeSnapshot.path !== latestGlobalTrackForAutoPlay.path)
    ) {
      clearGlobalAmbientResumeSnapshot();
    }
    scheduleAutoPlaybackFromContext();
  } catch (error) {
    console.error("[ThemeDeck] refresh auto playback cache failed", error);
  } finally {
    autoPlaybackTrackRefreshInFlight = false;
  }
};

const handleLaunchStopModeChanged = () => {
  void refreshRunningGameState();
  scheduleAutoPlaybackFromContext();
};

const startAutoPlaybackCoordinator = () => {
  if (autoPlaybackStarted) {
    return;
  }
  autoPlaybackStarted = true;
  ambientInterruptionModeRuntime = readAmbientInterruptionModeSetting();
  launchStopModeRuntime = readLaunchStopModeSetting();
  startDesktopModeWatcher();
  startRunningGameWatcher();
  refreshAutoPlaybackTrackCache();
  stopAutoPlaybackSubscription = subscribePlayback(() => {
    scheduleAutoPlaybackFromContext();
  });
  window.addEventListener(AUTO_PLAY_EVENT, scheduleAutoPlaybackFromContext);
  window.addEventListener(
    GLOBAL_AMBIENT_ENABLED_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.addEventListener(
    STORE_TRACK_ENABLED_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.addEventListener(
    AMBIENT_DISABLE_STORE_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.addEventListener(
    AMBIENT_INTERRUPTION_MODE_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.addEventListener(LAUNCH_STOP_MODE_EVENT, handleLaunchStopModeChanged);
  window.addEventListener(TRACKS_UPDATED_EVENT, refreshAutoPlaybackTrackCache);
  refreshStoreContext();
  autoPlaybackRouteInterval = window.setInterval(() => {
    scheduleAutoPlaybackFromContext();
    refreshStoreContext();
  }, 750);
};

const stopAutoPlaybackCoordinator = () => {
  if (!autoPlaybackStarted) {
    return;
  }
  autoPlaybackStarted = false;
  stopRunningGameWatcher();
  stopAutoPlaybackSubscription?.();
  stopAutoPlaybackSubscription = null;
  window.removeEventListener(AUTO_PLAY_EVENT, scheduleAutoPlaybackFromContext);
  window.removeEventListener(
    GLOBAL_AMBIENT_ENABLED_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.removeEventListener(
    STORE_TRACK_ENABLED_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.removeEventListener(
    AMBIENT_DISABLE_STORE_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.removeEventListener(
    AMBIENT_INTERRUPTION_MODE_EVENT,
    scheduleAutoPlaybackFromContext
  );
  window.removeEventListener(
    LAUNCH_STOP_MODE_EVENT,
    handleLaunchStopModeChanged
  );
  window.removeEventListener(TRACKS_UPDATED_EVENT, refreshAutoPlaybackTrackCache);
  stopDesktopModeWatcher();
  if (autoPlaybackRouteInterval) {
    window.clearInterval(autoPlaybackRouteInterval);
    autoPlaybackRouteInterval = null;
  }
  storeContextActive = false;
};

const useTrackState = (options?: { silent?: boolean }) => {
  const [tracks, setTracks] = useState<TrackMap>({});
  const [globalTrack, setGlobalTrack] = useState<GlobalTrack | null>(null);
  const [storeTrack, setStoreTrack] = useState<StoreTrack | null>(null);
  const [loadingTracks, setLoadingTracks] = useState(true);
  const silent = options?.silent ?? false;

  const refreshTracks = useCallback(async () => {
    try {
      const [trackData, globalData, storeData] = await Promise.all([
        fetchTracks(),
        fetchGlobalTrack(),
        fetchStoreTrack(),
      ]);
      const normalizedTracks = normalizeTracks(trackData);
      const normalizedGlobal = normalizeGlobalTrack(globalData);
      const normalizedStore = normalizeGlobalTrack(storeData);
      setTracks(normalizedTracks);
      setGlobalTrack(normalizedGlobal);
      setStoreTrack(normalizedStore);
      latestTracksForAutoPlay = normalizedTracks;
      latestGlobalTrackForAutoPlay = normalizedGlobal;
      latestStoreTrackForAutoPlay = normalizedStore;
      scheduleAutoPlaybackFromContext();
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

  return {
    tracks,
    setTracks,
    globalTrack,
    setGlobalTrack,
    storeTrack,
    setStoreTrack,
    loadingTracks,
    refreshTracks,
  };
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

const getThemeDeckRouteAppId = (pathname?: string): number | null => {
  const path = pathname || window.location.pathname || "";
  const match = path.match(/\/themedeck\/(\d+)/);
  if (!match) return null;
  const parsed = Number.parseInt(match[1], 10);
  return Number.isNaN(parsed) || parsed <= 0 ? null : parsed;
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

const useAmbientDisableStoreSetting = (): [boolean, (value: boolean) => void] =>
  useBooleanPreference(
    readAmbientDisableStoreSetting,
    persistAmbientDisableStoreSetting,
    AMBIENT_DISABLE_STORE_EVENT
  );

const useGlobalAmbientEnabledSetting = (): [boolean, (value: boolean) => void] =>
  useBooleanPreference(
    readGlobalAmbientEnabledSetting,
    persistGlobalAmbientEnabledSetting,
    GLOBAL_AMBIENT_ENABLED_EVENT
  );

const useStoreTrackEnabledSetting = (): [boolean, (value: boolean) => void] =>
  useBooleanPreference(
    readStoreTrackEnabledSetting,
    persistStoreTrackEnabledSetting,
    STORE_TRACK_ENABLED_EVENT
  );

const useAmbientInterruptionModeSetting = (): [
  AmbientInterruptionMode,
  (value: AmbientInterruptionMode) => void
] => {
  const [mode, setMode] = useState<AmbientInterruptionMode>(
    readAmbientInterruptionModeSetting()
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<AmbientInterruptionMode>).detail;
      setMode(parseAmbientInterruptionMode(detail));
    };
    window.addEventListener(
      AMBIENT_INTERRUPTION_MODE_EVENT,
      handler as EventListener
    );
    return () =>
      window.removeEventListener(
        AMBIENT_INTERRUPTION_MODE_EVENT,
        handler as EventListener
      );
  }, []);

  const update = useCallback((value: AmbientInterruptionMode) => {
    const normalized = parseAmbientInterruptionMode(value);
    setMode(normalized);
    if (normalized === "stop") {
      clearGlobalAmbientResumeSnapshot();
    }
    persistAmbientInterruptionModeSetting(normalized);
  }, []);

  return [mode, update];
};

const useLaunchStopModeSetting = (): [
  LaunchStopMode,
  (value: LaunchStopMode) => void
] => {
  const [mode, setMode] = useState<LaunchStopMode>(readLaunchStopModeSetting());

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<LaunchStopMode>).detail;
      setMode(parseLaunchStopMode(detail));
    };
    window.addEventListener(LAUNCH_STOP_MODE_EVENT, handler as EventListener);
    return () =>
      window.removeEventListener(LAUNCH_STOP_MODE_EVENT, handler as EventListener);
  }, []);

  const update = useCallback((value: LaunchStopMode) => {
    const normalized = parseLaunchStopMode(value);
    setMode(normalized);
    persistLaunchStopModeSetting(normalized);
  }, []);

  return [mode, update];
};


const Content = () => {
  const {
    tracks,
    setTracks,
    globalTrack,
    setGlobalTrack,
    storeTrack,
    setStoreTrack,
    loadingTracks,
  } = useTrackState();
  const [library, setLibrary] = useState<GameOption[]>([]);
  const [autoPlay, setAutoPlay] = useAutoPlaySetting();
  const [globalAmbientEnabled, setGlobalAmbientEnabled] =
    useGlobalAmbientEnabledSetting();
  const [storeTrackEnabled, setStoreTrackEnabled] = useStoreTrackEnabledSetting();
  const [ambientDisableStore, setAmbientDisableStore] =
    useAmbientDisableStoreSetting();
  const [ambientInterruptionMode, setAmbientInterruptionMode] =
    useAmbientInterruptionModeSetting();
  const [launchStopMode, setLaunchStopMode] = useLaunchStopModeSetting();
  const [ytDlpStatus, setYtDlpStatus] = useState<YtDlpStatus>({
    installed: false,
  });
  const [ytDlpBusy, setYtDlpBusy] = useState(false);
  const [bulkAssign, setBulkAssign] = useState<BulkAssignStatus>({
    running: false,
    stopRequested: false,
    total: 0,
    completed: 0,
    assigned: 0,
    skipped: 0,
    failed: 0,
    currentGame: "",
    message: "",
  });
  const bulkAssignStopRequestedRef = useRef(false);
  const bulkAssignRunIdRef = useRef(0);
  const [showMissingGames, setShowMissingGames] = useState(false);
  const [resolvedMissingNames, setResolvedMissingNames] = useState<Record<number, string>>(
    {}
  );
  const [failedMissingNameIds, setFailedMissingNameIds] = useState<Record<number, true>>(
    {}
  );
  const missingNameAttemptsRef = useRef<Map<number, number>>(new Map());
  const resolvingMissingNameIdsRef = useRef<Set<number>>(new Set());
  const [missingResolveInFlightCount, setMissingResolveInFlightCount] = useState(0);
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
  const libraryGames = useMemo(() => {
    const seen = new Set<number>();
    const unique: GameOption[] = [];
    for (const game of library) {
      if (!game || !Number.isFinite(game.appid) || game.appid <= 0) {
        continue;
      }
      if (seen.has(game.appid)) {
        continue;
      }
      seen.add(game.appid);
      unique.push(game);
    }
    return unique;
  }, [library]);
  const unassignedLibraryGameCount = useMemo(
    () => libraryGames.filter((game) => !tracks[game.appid]).length,
    [libraryGames, tracks]
  );
  const missingGamesStatus = useMemo(() => {
    const unknownNamePattern = /^App\s+\d+$/i;
    return libraryGames
      .filter((game) => !tracks[game.appid])
      .map((game) => {
        const resolvedName = String(resolvedMissingNames[game.appid] || "").trim();
        const baseName = String(getGameName(game.appid) || game.name || "").trim();
        const fallbackName = resolvedName || baseName;
        const isUnknown = !fallbackName || unknownNamePattern.test(fallbackName);
        const failed = !!failedMissingNameIds[game.appid];
        const status: "resolved" | "pending" | "failed" = isUnknown
          ? failed
            ? "failed"
            : "pending"
          : "resolved";
        const name =
          status === "failed"
            ? "Name unavailable"
            : fallbackName;
        return {
          appid: game.appid,
          name,
          status,
        };
      })
      .sort((a, b) => {
        if (a.status !== b.status) {
          if (a.status === "resolved") return -1;
          if (b.status === "resolved") return 1;
          if (a.status === "failed") return 1;
          if (b.status === "failed") return -1;
        }
        return a.name.localeCompare(b.name);
      });
  }, [libraryGames, tracks, getGameName, resolvedMissingNames, failedMissingNameIds]);

  const missingGamesList = useMemo(
    () => missingGamesStatus.filter((game) => game.status !== "pending"),
    [missingGamesStatus]
  );

  const missingGameNameStats = useMemo(() => {
    const total = missingGamesStatus.length;
    const resolved = missingGamesStatus.filter(
      (game) => game.status === "resolved"
    ).length;
    const failed = missingGamesStatus.filter(
      (game) => game.status === "failed"
    ).length;
    const pending = Math.max(0, total - resolved - failed);
    const processed = resolved + failed;
    const percent = total > 0 ? Math.round((processed / total) * 100) : 100;
    return { total, resolved, failed, pending, processed, percent };
  }, [missingGamesStatus]);

  const unresolvedMissingGameIds = useMemo(() => {
    return missingGamesStatus
      .filter((game) => game.status === "pending")
      .map((game) => game.appid);
  }, [missingGamesStatus]);

  useEffect(() => {
    const activeMissingIds = new Set(
      libraryGames
        .filter((game) => !tracks[game.appid])
        .map((game) => game.appid)
    );

    setResolvedMissingNames((prev) => {
      let changed = false;
      const next: Record<number, string> = {};
      for (const [idRaw, name] of Object.entries(prev)) {
        const appId = Number.parseInt(idRaw, 10);
        if (activeMissingIds.has(appId)) {
          next[appId] = name;
        } else {
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    setFailedMissingNameIds((prev) => {
      let changed = false;
      const next: Record<number, true> = {};
      for (const idRaw of Object.keys(prev)) {
        const appId = Number.parseInt(idRaw, 10);
        if (activeMissingIds.has(appId)) {
          next[appId] = true;
        } else {
          changed = true;
        }
      }
      return changed ? next : prev;
    });

    for (const appId of Array.from(missingNameAttemptsRef.current.keys())) {
      if (!activeMissingIds.has(appId)) {
        missingNameAttemptsRef.current.delete(appId);
      }
    }
    for (const appId of Array.from(resolvingMissingNameIdsRef.current.values())) {
      if (!activeMissingIds.has(appId)) {
        resolvingMissingNameIdsRef.current.delete(appId);
      }
    }
    setMissingResolveInFlightCount(resolvingMissingNameIdsRef.current.size);
  }, [libraryGames, tracks]);

  useEffect(() => {
    if (!showMissingGames) {
      return;
    }

    let cancelled = false;
    const resolveBatch = async () => {
      if (cancelled) {
        return;
      }
      if (!unresolvedMissingGameIds.length) {
        return;
      }
      const idsToResolve = unresolvedMissingGameIds
        .filter((appId) => !resolvingMissingNameIdsRef.current.has(appId))
        .slice(0, 6);
      if (!idsToResolve.length) {
        return;
      }

      idsToResolve.forEach((appId) => {
        resolvingMissingNameIdsRef.current.add(appId);
      });
      setMissingResolveInFlightCount(resolvingMissingNameIdsRef.current.size);

      try {
        const resolved = await resolveStoreAppNames(idsToResolve);
        if (cancelled || !resolved || typeof resolved !== "object") {
          return;
        }
        const updates: Record<number, string> = {};
        const resolvedIdSet = new Set<number>();
        for (const [idRaw, nameRaw] of Object.entries(resolved)) {
          const appId = Number.parseInt(idRaw, 10);
          const name = String(nameRaw || "").trim();
          if (!Number.isFinite(appId) || appId <= 0 || !name) {
            continue;
          }
          updates[appId] = name;
          resolvedIdSet.add(appId);
          missingNameAttemptsRef.current.delete(appId);
        }

        const failedNow: number[] = [];
        for (const appId of idsToResolve) {
          if (resolvedIdSet.has(appId)) {
            continue;
          }
          const attempts = (missingNameAttemptsRef.current.get(appId) || 0) + 1;
          missingNameAttemptsRef.current.set(appId, attempts);
          if (attempts >= 3) {
            failedNow.push(appId);
            missingNameAttemptsRef.current.delete(appId);
          }
        }

        if (Object.keys(updates).length) {
          setResolvedMissingNames((prev) => ({
            ...prev,
            ...updates,
          }));
        }
        if (Object.keys(updates).length || failedNow.length) {
          setFailedMissingNameIds((prev) => {
            const next = { ...prev };
            for (const appId of Object.keys(updates).map((id) => Number(id))) {
              delete next[appId];
            }
            for (const appId of failedNow) {
              next[appId] = true;
            }
            return next;
          });
        }
      } catch (error) {
        console.error("[ThemeDeck] failed to resolve missing game names", error);
      } finally {
        idsToResolve.forEach((appId) =>
          resolvingMissingNameIdsRef.current.delete(appId)
        );
        setMissingResolveInFlightCount(resolvingMissingNameIdsRef.current.size);
      }
    };

    void resolveBatch();
    const intervalId = window.setInterval(() => {
      void resolveBatch();
    }, 1800);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [showMissingGames, unresolvedMissingGameIds]);
  const loadLibrary = useCallback(async () => {
    try {
      const byId = new Map<number, GameOption>();
      const addEntry = (entry: any, fallbackId?: unknown) => {
        const fallbackAppId = Number.parseInt(String(fallbackId ?? ""), 10);
        let appid = Number.NaN;
        let nameCandidate: string | undefined;

        if (entry && typeof entry === "object") {
          const appidRaw =
            entry?.appid ??
            entry?.app_id ??
            entry?.unAppID ??
            entry?.nAppID ??
            entry?.id ??
            fallbackId;
          appid = Number.parseInt(String(appidRaw ?? ""), 10);
          nameCandidate =
            entry?.display_name ||
            entry?.localized_name ||
            entry?.name ||
            entry?.strTitle ||
            entry?.title;
        } else if (typeof entry === "number" || typeof entry === "bigint") {
          appid = Number(entry);
        } else if (typeof entry === "string") {
          const entryAsId = Number.parseInt(entry, 10);
          if (Number.isFinite(entryAsId) && entryAsId > 0) {
            appid = entryAsId;
          } else if (Number.isFinite(fallbackAppId) && fallbackAppId > 0) {
            appid = fallbackAppId;
            nameCandidate = entry;
          }
        } else if (Number.isFinite(fallbackAppId) && fallbackAppId > 0) {
          appid = fallbackAppId;
        }

        if (!Number.isFinite(appid) || appid <= 0) {
          return;
        }
        if (LIBRARY_EXCLUDED_APP_IDS.has(appid)) {
          return;
        }
        const overview =
          appStore?.GetAppOverviewByAppID?.(appid) ||
          appStore?.GetAppOverviewByGameID?.(appid);
        const appType = Number(overview?.app_type ?? entry?.app_type ?? NaN);
        const isDlc = Number.isFinite(appType) && (appType & (1 << 5)) !== 0;
        if (isDlc) {
          return;
        }
        if (overview?.visible_in_game_list === false) {
          return;
        }
        const name = String(
          overview?.display_name ||
            overview?.localized_name ||
            overview?.name ||
            nameCandidate ||
            getDisplayName(appid) ||
            `App ${appid}`
        );
        const existing = byId.get(appid);
        if (!existing || existing.name.startsWith("App ")) {
          byId.set(appid, { appid, name });
        }
      };
      const addCollection = (raw: any) => {
        if (!raw) {
          return;
        }
        if (Array.isArray(raw)) {
          raw.forEach((entry) => addEntry(entry));
          return;
        }
        if (raw instanceof Set) {
          raw.forEach((value) => addEntry(value));
          return;
        }
        if (raw instanceof Map) {
          raw.forEach((value, key) => addEntry(value, key));
          return;
        }
        if (typeof raw === "object") {
          Object.entries(raw).forEach(([key, value]) => addEntry(value, key));
          addEntry(raw);
        }
      };

      const steamApps = (window as any)?.SteamClient?.Apps;
      const appStore = (window as any)?.appStore;
      const bootstrap =
        steamApps?.GetLibraryBootstrapData?.() ??
        appStore?.GetLibraryBootstrapData?.();
      addCollection(bootstrap?.library?.apps);
      addCollection(bootstrap?.apps);
      addCollection(bootstrap?.rgApps);

      addCollection(appStore?.m_mapAppOverview);
      addCollection(appStore?.m_mapAppData);
      addCollection(appStore?.m_mapOwnedApps);
      addCollection(appStore?.m_mapApps);
      addCollection(appStore?.m_rgApps);
      addCollection(appStore?.m_rgAppData);
      addCollection(appStore?.m_rgAppOverviews);
      addCollection(appStore?.m_rgOwnedApps);

      try {
        const ownedResponse = await Promise.resolve(steamApps?.GetOwnedGames?.());
        addCollection(ownedResponse?.apps);
        addCollection(ownedResponse?.rgApps);
        addCollection(ownedResponse?.games);
        addCollection(ownedResponse?.rgGames);
      } catch (_ignored) {
        // no-op
      }

      try {
        const localconfigAppIds = await fetchLocalconfigAppIds();
        addCollection(localconfigAppIds?.app_ids ?? []);
      } catch (error) {
        console.error("[ThemeDeck] localconfig app id fallback failed", error);
      }

      const games = Array.from(byId.values()).sort((a, b) =>
        a.name.localeCompare(b.name)
      );
      setLibrary(games);
      console.info("[ThemeDeck] library detection count", games.length);
    } catch (error) {
      console.error("[ThemeDeck] library load failed", error);
    }
  }, []);

  useEffect(() => {
    void loadLibrary();
    const intervalId = window.setInterval(() => {
      void loadLibrary();
    }, 5000);
    const timeoutId = window.setTimeout(() => {
      window.clearInterval(intervalId);
    }, 30000);
    return () => {
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, [loadLibrary]);

  const refreshYtDlpStatus = useCallback(async () => {
    try {
      const status = await getYtDlpStatus();
      setYtDlpStatus(status);
    } catch (error) {
      console.error("[ThemeDeck] yt-dlp status failed", error);
    }
  }, []);

  useEffect(() => {
    refreshYtDlpStatus();
  }, [refreshYtDlpStatus]);

  const handleUpdateYtDlp = async () => {
    const confirmed = window.confirm(
      "Update yt-dlp now? Only do this if YouTube search is not working."
    );
    if (!confirmed) {
      return;
    }
    setYtDlpBusy(true);
    try {
      const status = await updateYtDlp();
      setYtDlpStatus(status);
      toaster.toast({
        title: "ThemeDeck",
        body: `yt-dlp ready (${status.version || "latest"})`,
      });
    } catch (error) {
      console.error("[ThemeDeck] update yt-dlp failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: `Failed to update yt-dlp: ${getErrorMessage(
          error,
          "Unknown update error"
        )}`,
      });
    } finally {
      setYtDlpBusy(false);
      refreshYtDlpStatus();
    }
  };

  const handleStopBulkAssign = useCallback(() => {
    if (!bulkAssign.running) {
      return;
    }
    bulkAssignStopRequestedRef.current = true;
    setBulkAssign((prev) => ({
      ...prev,
      stopRequested: true,
      message: "Stopping after current operation...",
    }));
  }, [bulkAssign.running]);

  const handleAutoAssignMissingTracks = useCallback(async () => {
    if (bulkAssign.running || ytDlpBusy) {
      return;
    }
    if (!ytDlpStatus.installed) {
      toaster.toast({
        title: "ThemeDeck",
        body: "yt-dlp is not installed yet.",
      });
      return;
    }
    if (!libraryGames.length) {
      toaster.toast({
        title: "ThemeDeck",
        body: "No games found in library.",
      });
      return;
    }

    let latestTracks = tracks;
    try {
      latestTracks = normalizeTracks(await fetchTracks());
    } catch (_ignored) {
      // Keep using current in-memory tracks if refresh fails.
    }

    const allMissingGames = libraryGames.filter((game) => !latestTracks[game.appid]);
    if (!allMissingGames.length) {
      toaster.toast({
        title: "ThemeDeck",
        body: "All library games already have assigned music.",
      });
      return;
    }

    const unknownNamePattern = /^App\s+\d+$/i;
    const resolvedNameById = new Map<number, string>();
    for (const game of allMissingGames) {
      const baseName = getGameName(game.appid) || game.name || `App ${game.appid}`;
      if (baseName && !unknownNamePattern.test(baseName.trim())) {
        resolvedNameById.set(game.appid, baseName);
      }
    }

    const unresolvedIds = allMissingGames
      .map((game) => game.appid)
      .filter((appId) => !resolvedNameById.has(appId));

    if (unresolvedIds.length) {
      try {
        const resolvedFromStore = await resolveStoreAppNames(unresolvedIds);
        for (const [idRaw, nameRaw] of Object.entries(resolvedFromStore || {})) {
          const appId = Number.parseInt(idRaw, 10);
          const name = String(nameRaw || "").trim();
          if (!Number.isFinite(appId) || appId <= 0 || !name) {
            continue;
          }
          resolvedNameById.set(appId, name);
        }
      } catch (error) {
        console.error("[ThemeDeck] resolve store app names failed", error);
      }
    }

    const getSearchName = (game: GameOption): string =>
      (resolvedNameById.get(game.appid) ||
        getGameName(game.appid) ||
        game.name ||
        `App ${game.appid}`) as string;

    const missingGames = allMissingGames;
    const unknownNameCount = allMissingGames.filter((game) =>
      unknownNamePattern.test(getSearchName(game).trim())
    ).length;

    const runId = Date.now();
    bulkAssignRunIdRef.current = runId;
    bulkAssignStopRequestedRef.current = false;

    let completed = 0;
    let assigned = 0;
    let skipped = 0;
    let failed = 0;

    setBulkAssign({
      running: true,
      stopRequested: false,
      total: missingGames.length,
      completed: 0,
      assigned: 0,
      skipped: 0,
      failed: 0,
      currentGame: "",
      message:
        unknownNameCount > 0
          ? `Preparing bulk assignment... (${unknownNameCount} unnamed games will still be attempted)`
          : "Preparing bulk assignment...",
    });

    for (const game of missingGames) {
      if (
        bulkAssignRunIdRef.current !== runId ||
        bulkAssignStopRequestedRef.current
      ) {
        break;
      }

      const gameName = getSearchName(game);
      const isUnknownName = unknownNamePattern.test(gameName.trim());
      const baseSearchName = isUnknownName ? `Steam app ${game.appid}` : gameName;
      const queryCandidates = Array.from(
        new Set(
          isUnknownName
            ? [
                `Steam app ${game.appid} soundtrack`,
                `App ${game.appid} soundtrack`,
                `App ${game.appid} game music`,
              ]
            : [
                `${baseSearchName} soundtrack`,
                `${baseSearchName} OST`,
                `${baseSearchName} theme`,
                `${baseSearchName} game music`,
                baseSearchName,
              ]
        )
      );

      try {
        latestTracks = normalizeTracks(await fetchTracks());
      } catch (_ignored) {
        latestTracks = tracks;
      }
      if (latestTracks[game.appid]) {
        completed += 1;
        skipped += 1;
        setBulkAssign((prev) => ({
          ...prev,
          completed,
          skipped,
          currentGame: gameName,
          message: `Skipped ${gameName} (already assigned).`,
        }));
        continue;
      }

      const candidateResults: YouTubeSearchResult[] = [];
      const seenVideoIds = new Set<string>();
      let hadSearchError = false;
      let searchErrorSummary = "";
      for (const query of queryCandidates) {
        if (
          bulkAssignRunIdRef.current !== runId ||
          bulkAssignStopRequestedRef.current
        ) {
          break;
        }
        setBulkAssign((prev) => ({
          ...prev,
          currentGame: gameName,
          message: `Searching YouTube for ${gameName} (${query})...`,
        }));
        try {
          const response = await searchYouTube(query, 5);
          const results = response?.results || [];
          for (const result of results) {
            if (!result?.id || seenVideoIds.has(result.id)) {
              continue;
            }
            seenVideoIds.add(result.id);
            candidateResults.push(result);
            if (candidateResults.length >= 8) {
              break;
            }
          }
          if (candidateResults.length >= 3) {
            break;
          }
        } catch (error) {
          hadSearchError = true;
          searchErrorSummary = getErrorMessage(error, "Unknown search error");
        }
      }

      if (
        bulkAssignRunIdRef.current !== runId ||
        bulkAssignStopRequestedRef.current
      ) {
        break;
      }

      if (!candidateResults.length) {
        completed += 1;
        if (hadSearchError) {
          failed += 1;
        } else {
          skipped += 1;
        }
        setBulkAssign((prev) => ({
          ...prev,
          completed,
          skipped,
          failed,
          currentGame: gameName,
          message: hadSearchError
            ? `Search failed for ${gameName}: ${searchErrorSummary}`
            : `No eligible YouTube results for ${gameName}.`,
        }));
        continue;
      }

      try {
        latestTracks = normalizeTracks(await fetchTracks());
      } catch (_ignored) {
        latestTracks = tracks;
      }
      if (latestTracks[game.appid]) {
        completed += 1;
        skipped += 1;
        setBulkAssign((prev) => ({
          ...prev,
          completed,
          skipped,
          currentGame: gameName,
          message: `Skipped ${gameName} (already assigned).`,
        }));
        continue;
      }

      let assignedCurrentGame = false;
      let lastDownloadError = "";
      for (let index = 0; index < candidateResults.length; index += 1) {
        if (
          bulkAssignRunIdRef.current !== runId ||
          bulkAssignStopRequestedRef.current
        ) {
          break;
        }
        const result = candidateResults[index];
        setBulkAssign((prev) => ({
          ...prev,
          currentGame: gameName,
          message: `Downloading match ${index + 1}/${candidateResults.length} for ${gameName}...`,
        }));

        try {
          const response = await downloadYouTubeAudio(game.appid, result.webpage_url);
          const normalized = normalizeTracks(response?.tracks);
          latestTracks = normalized;
          setTracks(normalized);
          latestTracksForAutoPlay = normalized;
          window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
          assigned += 1;
          completed += 1;
          assignedCurrentGame = true;
          setBulkAssign((prev) => ({
            ...prev,
            completed,
            assigned,
            currentGame: gameName,
            message: `Assigned ${gameName}.`,
          }));
          break;
        } catch (error) {
          lastDownloadError = getErrorMessage(error, "Unknown download error");
        }
      }

      if (!assignedCurrentGame) {
        completed += 1;
        failed += 1;
        setBulkAssign((prev) => ({
          ...prev,
          completed,
          failed,
          currentGame: gameName,
          message: `All download attempts failed for ${gameName}: ${lastDownloadError || "No usable results"}`,
        }));
      }
    }

    if (bulkAssignRunIdRef.current !== runId) {
      return;
    }

    const wasStopped = bulkAssignStopRequestedRef.current;
    bulkAssignStopRequestedRef.current = false;
    setBulkAssign((prev) => ({
      ...prev,
      running: false,
      stopRequested: false,
      currentGame: "",
      message: wasStopped
        ? `Stopped. Assigned ${assigned}, skipped ${skipped}, failed ${failed}.`
        : `Done. Assigned ${assigned}, skipped ${skipped}, failed ${failed}.`,
    }));

    toaster.toast({
      title: "ThemeDeck",
      body: wasStopped
        ? `Bulk assign stopped. Assigned ${assigned}, skipped ${skipped}, failed ${failed}.`
        : `Bulk assign complete. Assigned ${assigned}, skipped ${skipped}, failed ${failed}.`,
    });
  }, [
    bulkAssign.running,
    getGameName,
    libraryGames,
    tracks,
    ytDlpBusy,
    ytDlpStatus.installed,
    setTracks,
  ]);

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

  const handleGlobalPreviewToggle = () => {
    if (!globalTrack) return;
    if (
      playback.appId === GLOBAL_AMBIENT_APP_ID &&
      playback.status === "playing"
    ) {
      stopPlayback(false);
      return;
    }
    playTrack(
      {
        appId: GLOBAL_AMBIENT_APP_ID,
        path: globalTrack.path,
        filename: globalTrack.filename,
        volume: globalTrack.volume,
        startOffset: globalTrack.startOffset,
      },
      "manual"
    );
  };

  const handleGlobalVolumeChange = async (value: number) => {
    if (!globalTrack) return;
    const normalizedVolume = clamp(value / 100);
    const nextGlobal = { ...globalTrack, volume: normalizedVolume };
    setGlobalTrack(nextGlobal);
    latestGlobalTrackForAutoPlay = nextGlobal;
    applyVolumeToActiveTrack(GLOBAL_AMBIENT_APP_ID, normalizedVolume);
    try {
      const updated = await updateGlobalVolume(normalizedVolume);
      const normalized = normalizeGlobalTrack(updated);
      setGlobalTrack(normalized);
      latestGlobalTrackForAutoPlay = normalized;
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
    } catch (error) {
      console.error("[ThemeDeck] global volume update failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Couldn't save global track volume",
      });
    }
  };

  const handleGlobalStartOffsetChange = async (value: number) => {
    if (!globalTrack) return;
    const normalizedOffset = clamp(value, 0, 30);
    const nextGlobal = { ...globalTrack, startOffset: normalizedOffset };
    setGlobalTrack(nextGlobal);
    latestGlobalTrackForAutoPlay = nextGlobal;
    applyStartOffsetToActiveTrack(GLOBAL_AMBIENT_APP_ID, normalizedOffset);
    try {
      const updated = await updateGlobalStartOffset(normalizedOffset);
      const normalized = normalizeGlobalTrack(updated);
      setGlobalTrack(normalized);
      latestGlobalTrackForAutoPlay = normalized;
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
    } catch (error) {
      console.error("[ThemeDeck] global start offset update failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Couldn't save global song start truncation",
      });
    }
  };

  const handleRemoveGlobalTrack = async () => {
    if (!globalTrack) return;
    try {
      const removedPath = globalTrack.path;
      const updated = await deleteGlobalTrack();
      const normalized = normalizeTracks(updated);
      setTracks(normalized);
      setGlobalTrack(null);
      latestTracksForAutoPlay = normalized;
      latestGlobalTrackForAutoPlay = null;
      clearGlobalAmbientResumeSnapshot();
      clearAudioCache(removedPath);
      if (playback.appId === GLOBAL_AMBIENT_APP_ID) {
        stopPlayback(true);
      }
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
    } catch (error) {
      console.error("[ThemeDeck] remove global track failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Failed to remove global track",
      });
    }
  };

  const handleStorePreviewToggle = () => {
    if (!storeTrack) return;
    if (playback.appId === STORE_TRACK_APP_ID && playback.status === "playing") {
      stopPlayback(false);
      return;
    }
    playTrack(
      {
        appId: STORE_TRACK_APP_ID,
        path: storeTrack.path,
        filename: storeTrack.filename,
        volume: storeTrack.volume,
        startOffset: storeTrack.startOffset,
      },
      "manual"
    );
  };

  const handleStoreVolumeChange = async (value: number) => {
    if (!storeTrack) return;
    const normalizedVolume = clamp(value / 100);
    const nextStore = { ...storeTrack, volume: normalizedVolume };
    setStoreTrack(nextStore);
    latestStoreTrackForAutoPlay = nextStore;
    applyVolumeToActiveTrack(STORE_TRACK_APP_ID, normalizedVolume);
    try {
      const updated = await updateStoreVolume(normalizedVolume);
      const normalized = normalizeGlobalTrack(updated);
      setStoreTrack(normalized);
      latestStoreTrackForAutoPlay = normalized;
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
    } catch (error) {
      console.error("[ThemeDeck] store volume update failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Couldn't save store track volume",
      });
    }
  };

  const handleStoreStartOffsetChange = async (value: number) => {
    if (!storeTrack) return;
    const normalizedOffset = clamp(value, 0, 30);
    const nextStore = { ...storeTrack, startOffset: normalizedOffset };
    setStoreTrack(nextStore);
    latestStoreTrackForAutoPlay = nextStore;
    applyStartOffsetToActiveTrack(STORE_TRACK_APP_ID, normalizedOffset);
    try {
      const updated = await updateStoreStartOffset(normalizedOffset);
      const normalized = normalizeGlobalTrack(updated);
      setStoreTrack(normalized);
      latestStoreTrackForAutoPlay = normalized;
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
    } catch (error) {
      console.error("[ThemeDeck] store start offset update failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Couldn't save store song start truncation",
      });
    }
  };

  const handleRemoveStoreTrack = async () => {
    if (!storeTrack) return;
    try {
      const removedPath = storeTrack.path;
      const updated = await deleteStoreTrack();
      const normalized = normalizeTracks(updated);
      setTracks(normalized);
      setStoreTrack(null);
      latestTracksForAutoPlay = normalized;
      latestStoreTrackForAutoPlay = null;
      clearAudioCache(removedPath);
      if (playback.appId === STORE_TRACK_APP_ID) {
        stopPlayback(true);
      }
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
    } catch (error) {
      console.error("[ThemeDeck] remove store track failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Failed to remove store track",
      });
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

  const handleStartOffsetChange = async (appId: number, value: number) => {
    const normalizedOffset = clamp(value, 0, 30);
    setTracks((prev) => ({
      ...prev,
      [appId]: {
        ...prev[appId],
        startOffset: normalizedOffset,
      },
    }));
    applyStartOffsetToActiveTrack(appId, normalizedOffset);

    try {
      const updated = await updateTrackStartOffset(appId, normalizedOffset);
      setTracks(normalizeTracks(updated));
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
    } catch (error) {
      console.error("[ThemeDeck] start offset update failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: "Couldn't save song start truncation",
      });
    }
  };

  useEffect(() => {
    topFocusRef.current?.focus();
  }, []);

  return (
    <ScrollPanel>
      <div
        className="themedeck-main"
        style={{
          paddingBottom: "1.5rem",
          paddingRight: "0.85rem",
          paddingLeft: "0.25rem",
          width: "100%",
          maxWidth: "100%",
          boxSizing: "border-box",
          overflowX: "hidden",
        }}
      >
      <style>{`
        .themedeck-main,
        .themedeck-main * {
          min-width: 0 !important;
          box-sizing: border-box !important;
        }
        .themedeck-main .themedeck-fit {
          width: calc(100% - 0.35rem) !important;
          max-width: calc(100% - 0.35rem) !important;
          min-width: 0 !important;
          margin-right: auto !important;
          box-sizing: border-box !important;
        }
        .themedeck-main .themedeck-wrap {
          white-space: normal !important;
          overflow-wrap: anywhere !important;
          word-break: break-word !important;
        }
        .themedeck-main [class*="PanelSectionRow"] {
          max-width: 100% !important;
          width: 100% !important;
          min-width: 0 !important;
        }
        .themedeck-main [class*="PanelSectionRow"] > * {
          max-width: 100% !important;
          min-width: 0 !important;
        }
        .themedeck-main [class*="FieldLabel"],
        .themedeck-main [class*="FieldDescription"],
        .themedeck-main [class*="ValueSuffix"],
        .themedeck-main [class*="Value"] {
          white-space: normal !important;
          overflow-wrap: anywhere !important;
          word-break: break-word !important;
        }
      `}</style>
      <div
        ref={topFocusRef}
        tabIndex={-1}
        style={{ position: "absolute", width: 0, height: 0, outline: "none" }}
      />
      <PanelSection>
        <PanelSectionRow>
          <div style={{ width: "100%", paddingTop: "0.2rem" }}>
            <div style={{ fontSize: "0.95rem", fontWeight: 700 }}>
              February 25, 2026 (v2.5.2)
            </div>
            <div style={{ fontSize: "0.86rem", opacity: 0.88, marginTop: "0.25rem" }}>
              To assign music tracks, go to a game's page, select the "gear" icon, then "Choose ThemeDeck music..."
            </div>
            <hr style={{ margin: "0.4rem 0" }} />
          </div>
        </PanelSectionRow>
      </PanelSection>
      <div style={{ marginTop: "-0.75rem" }}>
        <PanelSection>
          <PanelSectionRow>
            <ToggleField
              checked={autoPlay}
              label="Auto play on game page"
              description="Start music as soon as you open a game's details view."
              onChange={(value) => setAutoPlay(value)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <div style={{ width: "100%" }}>
              <div style={{ fontWeight: 600 }}>
                Stop music after pressing Play
              </div>
              <div style={{ opacity: 0.8, fontSize: "0.85rem" }}>
                Choose when ThemeDeck music should stop during game launch:
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.35rem",
                  marginTop: "0.45rem",
                }}
                role="radiogroup"
                aria-label="Stop music timing on launch"
              >
                {(
                  [
                    {
                      value: "launch_start",
                      label: "At launch start",
                    },
                    {
                      value: "game_started",
                      label: "At launch finish",
                    },
                  ] as Array<{ value: LaunchStopMode; label: string }>
                ).map((option) => (
                  <button
                    key={option.value}
                    className="DialogButton themedeck-fit themedeck-wrap"
                    onClick={() => setLaunchStopMode(option.value)}
                    role="radio"
                    aria-checked={launchStopMode === option.value}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      justifyContent: "flex-start",
                      width: "100%",
                      boxSizing: "border-box",
                      whiteSpace: "normal",
                      textAlign: "left",
                      fontSize: "0.92rem",
                      paddingRight: "0.65rem",
                      paddingLeft: "0.65rem",
                      border:
                        launchStopMode === option.value
                          ? "1px solid rgba(120, 180, 255, 0.85)"
                          : undefined,
                    }}
                  >
                    <span style={{ minWidth: "1.4rem", textAlign: "center" }}>
                      {launchStopMode === option.value ? "(x)" : "( )"}
                    </span>
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              checked={globalAmbientEnabled}
              label="Enable global/ambient track"
              description="Keep global track assigned, but toggle its playback on non-game pages."
              onChange={(value) => {
                setGlobalAmbientEnabled(value);
                scheduleAutoPlaybackFromContext();
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              checked={storeTrackEnabled}
              label="Enable store track"
              description="Keep store track assigned, but toggle its playback on store pages."
              onChange={(value) => {
                setStoreTrackEnabled(value);
                scheduleAutoPlaybackFromContext();
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              checked={ambientDisableStore}
              label="Disable global/ambient track while in game store"
              description="When enabled, global ambient music is muted on store pages."
              onChange={(value) => {
                setAmbientDisableStore(value);
                scheduleAutoPlaybackFromContext();
              }}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <div style={{ width: "100%" }}>
              <div style={{ fontWeight: 600 }}>
                Global/ambient interruption behavior
              </div>
              <div style={{ opacity: 0.8, fontSize: "0.85rem" }}>
                When game/store music interrupts global ambient:
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.35rem",
                  marginTop: "0.45rem",
                }}
                role="radiogroup"
                aria-label="Global ambient interruption behavior"
              >
                {(
                  [
                    {
                      value: "stop",
                      label: "Stop (restart)",
                    },
                    {
                      value: "pause",
                      label: "Pause",
                    },
                    {
                      value: "mute",
                      label: "Mute",
                    },
                  ] as Array<{ value: AmbientInterruptionMode; label: string }>
                ).map((option) => (
                  <button
                    key={option.value}
                    className="DialogButton themedeck-fit themedeck-wrap"
                    onClick={() => setAmbientInterruptionMode(option.value)}
                    role="radio"
                    aria-checked={ambientInterruptionMode === option.value}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      justifyContent: "flex-start",
                      width: "100%",
                      boxSizing: "border-box",
                      whiteSpace: "normal",
                      textAlign: "left",
                      fontSize: "0.92rem",
                      paddingRight: "0.65rem",
                      paddingLeft: "0.65rem",
                      border:
                        ambientInterruptionMode === option.value
                          ? "1px solid rgba(120, 180, 255, 0.85)"
                          : undefined,
                    }}
                  >
                    <span style={{ minWidth: "1.4rem", textAlign: "center" }}>
                      {ambientInterruptionMode === option.value ? "(x)" : "( )"}
                    </span>
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <button
              className="DialogButton themedeck-fit themedeck-wrap"
              onClick={() => Navigation.Navigate("/themedeck/global")}
              style={{
                textAlign: "left",
                fontSize: "0.92rem",
                paddingRight: "0.65rem",
                paddingLeft: "0.65rem",
              }}
            >
              Choose global/ambient track...
            </button>
          </PanelSectionRow>
          <PanelSectionRow>
            <button
              className="DialogButton themedeck-fit themedeck-wrap"
              onClick={() => Navigation.Navigate("/themedeck/store")}
              style={{
                textAlign: "left",
                fontSize: "0.92rem",
                paddingRight: "0.65rem",
                paddingLeft: "0.65rem",
              }}
            >
              Choose store-only track...
            </button>
          </PanelSectionRow>
          <PanelSectionRow>
            <div
              style={{
                width: "100%",
                display: "flex",
                flexDirection: "column",
                gap: "0.4rem",
                alignItems: "stretch",
              }}
            >
              <div style={{ color: "#ff6b6b", fontWeight: 700, fontSize: "0.86rem" }}>
                Only update yt-dlp if YouTube search doesn't work.
              </div>
              <div style={{ color: "#ff8f8f", fontSize: "0.84rem" }}>
                {ytDlpStatus.installed
                  ? `yt-dlp ${ytDlpStatus.version || ""}`.trim()
                  : "yt-dlp not installed"}
              </div>
              <button
                className="DialogButton themedeck-fit themedeck-wrap"
                onClick={handleUpdateYtDlp}
                disabled={ytDlpBusy}
                style={{
                  textAlign: "left",
                  fontSize: "0.92rem",
                  paddingRight: "0.65rem",
                  paddingLeft: "0.65rem",
                  color: "#ff6b6b",
                  border: "1px solid rgba(255, 107, 107, 0.7)",
                }}
              >
                {ytDlpBusy ? "Updating..." : "Update yt-dlp"}
              </button>
            </div>
          </PanelSectionRow>
        </PanelSection>
      </div>
      <PanelSection title="Auto-assign missing game tracks (yt-dlp)">
        <PanelSectionRow>
          <div style={{ width: "100%" }}>
            <div style={{ opacity: 0.8, fontSize: "0.85rem" }}>
              Uses first YouTube result per game and only targets games with no assigned track.
            </div>
            <div style={{ opacity: 0.95, fontSize: "0.88rem", marginTop: "0.25rem", fontWeight: 600 }}>
              Games currently without music assigned: {unassignedLibraryGameCount}
            </div>
            <div style={{ opacity: 0.75, fontSize: "0.8rem", marginTop: "0.15rem" }}>
              Total library games detected: {libraryGames.length}
            </div>
            <div
              style={{
                marginTop: "0.5rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.35rem",
                alignItems: "stretch",
              }}
            >
              <button
                className="DialogButton themedeck-fit themedeck-wrap"
                onClick={handleAutoAssignMissingTracks}
                disabled={
                  bulkAssign.running || ytDlpBusy || !ytDlpStatus.installed
                }
                style={{
                  textAlign: "left",
                  fontSize: "0.92rem",
                  paddingRight: "0.65rem",
                  paddingLeft: "0.65rem",
                }}
              >
                {bulkAssign.running ? "Running..." : "Auto-assign missing"}
              </button>
              <button
                className="DialogButton themedeck-fit themedeck-wrap"
                onClick={handleStopBulkAssign}
                disabled={!bulkAssign.running}
                style={{
                  fontSize: "0.92rem",
                  paddingRight: "0.65rem",
                  paddingLeft: "0.65rem",
                }}
              >
                STOP
              </button>
            </div>
            {(bulkAssign.running || bulkAssign.message) && (
              <div style={{ marginTop: "0.55rem" }}>
                <div
                  style={{
                    width: "100%",
                    height: "0.55rem",
                    borderRadius: "0.35rem",
                    background: "rgba(255,255,255,0.18)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${
                        bulkAssign.total > 0
                          ? Math.min(
                              100,
                              Math.round((bulkAssign.completed / bulkAssign.total) * 100)
                            )
                          : 0
                      }%`,
                      height: "100%",
                      background: "rgba(98, 168, 255, 0.95)",
                      transition: "width 0.2s ease",
                    }}
                  />
                </div>
                <div style={{ marginTop: "0.35rem", fontSize: "0.82rem", opacity: 0.85 }}>
                  {bulkAssign.completed}/{bulkAssign.total} completed
                  {" • "}assigned {bulkAssign.assigned}
                </div>
                <div style={{ marginTop: "0.15rem", fontSize: "0.82rem", opacity: 0.85 }}>
                  skipped {bulkAssign.skipped}
                  {" • "}failed {bulkAssign.failed}
                </div>
                {bulkAssign.currentGame && (
                  <div style={{ marginTop: "0.2rem", fontSize: "0.82rem", opacity: 0.85 }}>
                    Current game: {bulkAssign.currentGame}
                    {bulkAssign.stopRequested ? " (stopping...)" : ""}
                  </div>
                )}
                {!!bulkAssign.message && (
                  <div style={{ marginTop: "0.2rem", fontSize: "0.82rem", opacity: 0.85 }}>
                    {bulkAssign.message}
                  </div>
                )}
              </div>
            )}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div
            style={{
              width: "100%",
              display: "flex",
              flexDirection: "column",
              gap: "0.45rem",
            }}
          >
            <button
              className="DialogButton themedeck-fit themedeck-wrap"
              onClick={() => setShowMissingGames((prev) => !prev)}
              style={{
                textAlign: "left",
                fontSize: "0.92rem",
                paddingRight: "0.65rem",
                paddingLeft: "0.65rem",
              }}
            >
              {showMissingGames ? "Hide games without music" : "Show games without music"}
            </button>
            {showMissingGames ? (
              <div
                style={{
                  width: "100%",
                  borderRadius: "0.4rem",
                  background: "rgba(255,255,255,0.05)",
                  padding: "0.55rem 0.65rem",
                  maxHeight: "16rem",
                  overflowY: "auto",
                  overflowX: "hidden",
                }}
              >
                {missingGameNameStats.total > 0 ? (
                  <>
                    <div style={{ fontSize: "0.82rem", opacity: 0.9, marginBottom: "0.35rem" }}>
                      {missingGameNameStats.resolved}/{missingGameNameStats.total} names resolved
                      {" • "}pending {missingGameNameStats.pending}
                      {" • "}unavailable {missingGameNameStats.failed}
                      {missingResolveInFlightCount > 0
                        ? ` • checking ${missingResolveInFlightCount}`
                        : ""}
                    </div>
                    <div
                      style={{
                        width: "100%",
                        height: "0.5rem",
                        borderRadius: "0.35rem",
                        background: "rgba(255,255,255,0.16)",
                        overflow: "hidden",
                        marginBottom: "0.45rem",
                      }}
                    >
                      <div
                        style={{
                          width: `${missingGameNameStats.percent}%`,
                          height: "100%",
                          background: "rgba(98, 168, 255, 0.95)",
                          transition: "width 0.25s ease",
                        }}
                      />
                    </div>
                    {missingGameNameStats.pending > 0 && missingGamesList.length === 0 ? (
                      <div style={{ opacity: 0.8, fontSize: "0.86rem", marginBottom: "0.25rem" }}>
                        Resolving game names...
                      </div>
                    ) : null}
                    {missingGamesList.map((game) => (
                      <div
                        key={game.appid}
                        style={{
                          padding: "0.22rem 0",
                          fontSize: "0.86rem",
                          overflowWrap: "anywhere",
                          wordBreak: "break-word",
                          color:
                            game.status === "failed"
                              ? "rgba(255, 200, 200, 0.92)"
                              : "inherit",
                        }}
                      >
                        {game.name} ({game.appid})
                      </div>
                    ))}
                  </>
                ) : (
                  <div style={{ opacity: 0.8, fontSize: "0.86rem" }}>
                    No games are missing music.
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Global / ambient track">
        {!globalTrack ? (
          <PanelSectionRow>
            <div>No global track selected.</div>
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <Focusable style={{ width: "100%" }}>
              <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                {globalTrack.filename}
              </div>
              <div style={{ opacity: 0.8, fontSize: "0.9rem", overflowWrap: "anywhere" }}>
                {globalTrack.path}
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
                    playback.appId === GLOBAL_AMBIENT_APP_ID &&
                    playback.status === "playing"
                      ? "Pause preview"
                      : "Preview track"
                  }
                  onClick={handleGlobalPreviewToggle}
                >
                  {playback.appId === GLOBAL_AMBIENT_APP_ID &&
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
                  title="Remove global ambient music"
                  onClick={handleRemoveGlobalTrack}
                >
                  <FaTrash />
                </button>
              </div>
              <div style={{ marginTop: "0.5rem" }}>
                <SliderField
                  value={Math.round(globalTrack.volume * 100)}
                  label="Volume"
                  min={0}
                  max={100}
                  step={5}
                  valueSuffix="%"
                  showValue
                  onChange={handleGlobalVolumeChange}
                />
              </div>
              <div style={{ marginTop: "0.35rem" }}>
                <SliderField
                  value={Math.round(globalTrack.startOffset)}
                  label="Start skip"
                  min={0}
                  max={30}
                  step={1}
                  valueSuffix="s"
                  showValue
                  onChange={handleGlobalStartOffsetChange}
                />
              </div>
            </Focusable>
          </PanelSectionRow>
        )}
      </PanelSection>
      <PanelSection title="Store-only track">
        {!storeTrack ? (
          <PanelSectionRow>
            <div>No store-only track selected.</div>
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <Focusable style={{ width: "100%" }}>
              <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                {storeTrack.filename}
              </div>
              <div style={{ opacity: 0.8, fontSize: "0.9rem", overflowWrap: "anywhere" }}>
                {storeTrack.path}
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
                    playback.appId === STORE_TRACK_APP_ID &&
                    playback.status === "playing"
                      ? "Pause preview"
                      : "Preview track"
                  }
                  onClick={handleStorePreviewToggle}
                >
                  {playback.appId === STORE_TRACK_APP_ID &&
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
                  title="Remove store-only music"
                  onClick={handleRemoveStoreTrack}
                >
                  <FaTrash />
                </button>
              </div>
              <div style={{ marginTop: "0.5rem" }}>
                <SliderField
                  value={Math.round(storeTrack.volume * 100)}
                  label="Volume"
                  min={0}
                  max={100}
                  step={5}
                  valueSuffix="%"
                  showValue
                  onChange={handleStoreVolumeChange}
                />
              </div>
              <div style={{ marginTop: "0.35rem" }}>
                <SliderField
                  value={Math.round(storeTrack.startOffset)}
                  label="Start skip"
                  min={0}
                  max={30}
                  step={1}
                  valueSuffix="s"
                  showValue
                  onChange={handleStoreStartOffsetChange}
                />
              </div>
            </Focusable>
          </PanelSectionRow>
        )}
      </PanelSection>
      <PanelSection title="Assigned tracks">
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
                <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>
                  {getGameName(track.appId)}
                </div>
                <div style={{ opacity: 0.8, fontSize: "0.9rem", overflowWrap: "anywhere" }}>
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
                <div style={{ marginTop: "0.5rem" }}>
                  <SliderField
                    value={Math.round(track.volume * 100)}
                    label="Volume"
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
                <div style={{ marginTop: "0.35rem" }}>
                  <SliderField
                    value={Math.round(track.startOffset)}
                    label="Start skip"
                    min={0}
                    max={30}
                    step={1}
                    valueSuffix="s"
                    showValue
                    onChange={(value) =>
                      handleStartOffsetChange(track.appId, value)
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
  const [ytDlpStatus, setYtDlpStatus] = useState<YtDlpStatus>({
    installed: false,
  });
  const [ytDlpBusy, setYtDlpBusy] = useState(false);
  const [youtubeQuery, setYoutubeQuery] = useState("");
  const [youtubeLoading, setYoutubeLoading] = useState(false);
  const [youtubeResults, setYoutubeResults] = useState<YouTubeSearchResult[]>([]);
  const [youtubeError, setYoutubeError] = useState("");
  const [downloadingVideoId, setDownloadingVideoId] = useState<string | null>(null);
  const [routePathname, setRoutePathname] = useState<string>(
    window.location.pathname || ""
  );
  const [selectedYouTubeId, setSelectedYouTubeId] = useState<string | null>(null);
  const topFocusRef = useRef<HTMLDivElement | null>(null);
  const assignedVideoId = useMemo(() => {
    if (!track?.filename) return "";
    const match = track.filename.match(/\[([A-Za-z0-9_-]{6,})\]\.[A-Za-z0-9]+$/);
    return match?.[1] ?? "";
  }, [track?.filename]);
  const [previewLoadingVideoId, setPreviewLoadingVideoId] = useState<string | null>(
    null
  );
  const [previewingVideoId, setPreviewingVideoId] = useState<string | null>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);

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

  useEffect(() => {
    let lastPath = window.location.pathname || "";
    const intervalId = window.setInterval(() => {
      const currentPath = window.location.pathname || "";
      if (currentPath !== lastPath) {
        lastPath = currentPath;
        setRoutePathname(currentPath);
      }
    }, 150);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const routeAppId = getThemeDeckRouteAppId(routePathname);
    const targetAppId = appId || routeAppId;
    if (!targetAppId) return;
    setYoutubeError("");
    setYoutubeResults([]);
    setYoutubeQuery("");
    const nextQuery = `${getDisplayName(targetAppId)} theme music`;
    setYoutubeQuery(nextQuery);
    const delayedRefresh = window.setTimeout(() => {
      setYoutubeQuery(`${getDisplayName(targetAppId)} theme music`);
    }, 250);
    return () => {
      window.clearTimeout(delayedRefresh);
    };
  }, [appId, routePathname]);

  useEffect(() => {
    if (!youtubeResults.length) {
      setSelectedYouTubeId(null);
      return;
    }
    const currentlySelected = youtubeResults.find((item) => item.id === selectedYouTubeId);
    if (!currentlySelected) {
      setSelectedYouTubeId(youtubeResults[0].id);
    }
  }, [youtubeResults, selectedYouTubeId]);

  const refreshYtDlpStatus = useCallback(
    async (silent = false) => {
      try {
        const status = await getYtDlpStatus();
        setYtDlpStatus(status);
      } catch (error) {
        console.error("[ThemeDeck] yt-dlp status failed", error);
        if (!silent) {
          toaster.toast({
            title: "ThemeDeck",
            body: "Failed to read yt-dlp status",
          });
        }
      }
    },
    []
  );

  useEffect(() => {
    refreshYtDlpStatus(true);
  }, [refreshYtDlpStatus]);

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

  useEffect(() => {
    topFocusRef.current?.focus();
  }, [appId]);

  useEffect(
    () => () => {
      const preview = previewAudioRef.current;
      if (preview) {
        preview.pause();
        preview.src = "";
        previewAudioRef.current = null;
      }
    },
    []
  );

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

  const handleYouTubeSearch = async () => {
    if (!ytDlpStatus.installed) {
      toaster.toast({
        title: "ThemeDeck",
        body: "yt-dlp is not installed yet. Press Install yt-dlp first.",
      });
      return;
    }
    const query = youtubeQuery.trim();
    if (!query) {
      toaster.toast({
        title: "ThemeDeck",
        body: "Enter a search query first",
      });
      return;
    }
    setYoutubeLoading(true);
    setYoutubeError("");
    try {
      const response = await searchYouTube(query, 20);
      setYoutubeResults(
        (response?.results ?? []).filter(
          (result) => !result.duration || result.duration <= 15 * 60
        )
      );
    } catch (error) {
      console.error("[ThemeDeck] youtube search failed", error);
      const message = getErrorMessage(error, "Unknown search error");
      setYoutubeError(message);
      toaster.toast({
        title: "ThemeDeck",
        body: `YouTube search failed: ${message}`,
      });
    } finally {
      setYoutubeLoading(false);
      refreshYtDlpStatus(true);
    }
  };

  const stopPreview = () => {
    const preview = previewAudioRef.current;
    if (!preview) return;
    preview.pause();
    preview.currentTime = 0;
    preview.src = "";
    setPreviewingVideoId(null);
  };

  const handleYouTubePreview = async (result: YouTubeSearchResult) => {
    if (previewingVideoId === result.id) {
      stopPreview();
      return;
    }
    setPreviewLoadingVideoId(result.id);
    try {
      const response = await getYouTubePreviewStream(result.webpage_url);
      const streamUrl = (response?.stream_url || "").trim();
      if (!streamUrl) {
        throw new Error("No preview stream URL returned");
      }
      let preview = previewAudioRef.current;
      if (!preview) {
        preview = new Audio();
        preview.preload = "none";
        previewAudioRef.current = preview;
      }
      preview.onended = () => {
        setPreviewingVideoId(null);
      };
      preview.onerror = () => {
        setPreviewingVideoId(null);
      };
      preview.pause();
      preview.currentTime = 0;
      preview.src = streamUrl;
      await preview.play();
      setPreviewingVideoId(result.id);
    } catch (error) {
      const message = getErrorMessage(error, "Preview failed");
      toaster.toast({
        title: "ThemeDeck",
        body: `Preview failed: ${message}`,
      });
      setPreviewingVideoId(null);
    } finally {
      setPreviewLoadingVideoId(null);
      refreshYtDlpStatus(true);
    }
  };

  const handleYouTubeDownload = async (result: YouTubeSearchResult) => {
    if (!appId) return;
    setDownloadingVideoId(result.id);
    try {
      const response = await downloadYouTubeAudio(appId, result.webpage_url);
      const normalized = normalizeTracks(response?.tracks);
      setTrack(normalized[appId] ?? null);
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      toaster.toast({
        title: "ThemeDeck",
        body: `Saved "${response.filename}" for ${getDisplayName(appId)}`,
      });
    } catch (error) {
      console.error("[ThemeDeck] youtube download failed", error);
      const message = getErrorMessage(error, "Unknown download error");
      toaster.toast({
        title: "ThemeDeck",
        body: `YouTube download failed: ${message}`,
      });
    } finally {
      setDownloadingVideoId(null);
      refreshYtDlpStatus(true);
    }
  };

  const selectedYouTubeResult = useMemo(
    () => youtubeResults.find((item) => item.id === selectedYouTubeId) ?? null,
    [youtubeResults, selectedYouTubeId]
  );

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
      <div
        ref={topFocusRef}
        tabIndex={-1}
        style={{ position: "absolute", width: 0, height: 0, outline: "none" }}
      />
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
          <div
            style={{
              width: "100%",
              display: "flex",
              gap: "0.5rem",
              flexWrap: "nowrap",
              alignItems: "center",
            }}
          >
            {track ? (
              <button
                className="DialogButton"
                onClick={handleRemove}
                style={{ minWidth: "8.5rem", whiteSpace: "nowrap" }}
              >
                Remove music
              </button>
            ) : null}
            <button
              className="DialogButton"
              onClick={() => Navigation.NavigateBack()}
              style={{ minWidth: "6rem", whiteSpace: "nowrap" }}
            >
              Done
            </button>
          </div>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="YouTube search (yt-dlp)">
        <PanelSectionRow>
          <div
            style={{
              width: "100%",
              display: "flex",
              flexDirection: "column",
              gap: "0.35rem",
            }}
          >
            <div style={{ fontWeight: 600 }}>
              {ytDlpStatus.installed
                ? `yt-dlp ${ytDlpStatus.version || ""}`.trim()
                : "yt-dlp not installed"}
            </div>
            {ytDlpStatus.path ? (
              <div style={{ fontFamily: "monospace", fontSize: "0.8rem", opacity: 0.8 }}>
                {ytDlpStatus.path}
              </div>
            ) : null}
            <div style={{ opacity: 0.8, fontSize: "0.85rem" }}>
              Search YouTube for game music, download audio locally, and assign it to
              this game.
            </div>
            {!ytDlpStatus.installed ? (
              <button
                className="DialogButton"
                onClick={async () => {
                  setYtDlpBusy(true);
                  try {
                    const status = await updateYtDlp();
                    setYtDlpStatus(status);
                    toaster.toast({
                      title: "ThemeDeck",
                      body: `yt-dlp ready (${status.version || "latest"})`,
                    });
                  } catch (error) {
                    toaster.toast({
                      title: "ThemeDeck",
                      body: `Failed to install yt-dlp: ${getErrorMessage(
                        error,
                        "Unknown update error"
                      )}`,
                    });
                  } finally {
                    setYtDlpBusy(false);
                    refreshYtDlpStatus(true);
                  }
                }}
                disabled={ytDlpBusy}
                style={{ width: "fit-content" }}
              >
                {ytDlpBusy ? "Installing..." : "Install yt-dlp"}
              </button>
            ) : null}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto",
              width: "100%",
              gap: "0.5rem",
              alignItems: "center",
            }}
          >
            <TextField
              value={youtubeQuery}
              onChange={(event) => setYoutubeQuery(event.target.value)}
              style={{ width: "100%", minWidth: "22rem" }}
            />
            <button
              className="DialogButton"
              onClick={handleYouTubeSearch}
              disabled={youtubeLoading || ytDlpBusy}
              style={{ minWidth: "12rem" }}
            >
              {youtubeLoading ? "Searching..." : "Search"}
            </button>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          {youtubeError ? (
            <div
              style={{
                width: "100%",
                padding: "0.55rem 0.7rem",
                borderRadius: "0.35rem",
                background: "rgba(255, 90, 90, 0.13)",
                color: "#ffd7d7",
                fontSize: "0.85rem",
                lineHeight: 1.35,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {youtubeError}
            </div>
          ) : null}
        </PanelSectionRow>
        <PanelSectionRow>
          {youtubeLoading ? (
            <Spinner />
          ) : (
            <div
              style={{
                width: "100%",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {!!selectedYouTubeResult && youtubeResults.length > 1 ? (
                <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                  <button
                    className="DialogButton"
                    onClick={() => {
                      const index = youtubeResults.findIndex((item) => item.id === selectedYouTubeResult.id);
                      const next = index <= 0 ? youtubeResults[youtubeResults.length - 1] : youtubeResults[index - 1];
                      setSelectedYouTubeId(next.id);
                    }}
                    style={{ minWidth: "6rem", whiteSpace: "nowrap" }}
                  >
                    Prev
                  </button>
                  <button
                    className="DialogButton"
                    onClick={() => {
                      const index = youtubeResults.findIndex((item) => item.id === selectedYouTubeResult.id);
                      const next = index >= youtubeResults.length - 1 ? youtubeResults[0] : youtubeResults[index + 1];
                      setSelectedYouTubeId(next.id);
                    }}
                    style={{ minWidth: "6rem", whiteSpace: "nowrap" }}
                  >
                    Next
                  </button>
                  <button
                    className="DialogButton"
                    onClick={() => handleYouTubePreview(selectedYouTubeResult)}
                    disabled={previewLoadingVideoId !== null || downloadingVideoId !== null}
                    style={{ minWidth: "8rem", whiteSpace: "nowrap" }}
                  >
                    {previewingVideoId === selectedYouTubeResult.id ? "Stop Preview" : "Play Preview"}
                  </button>
                  <button
                    className="DialogButton"
                    onClick={() => handleYouTubeDownload(selectedYouTubeResult)}
                    disabled={downloadingVideoId !== null}
                    style={{ minWidth: "11rem", whiteSpace: "nowrap" }}
                  >
                    {downloadingVideoId === selectedYouTubeResult.id ? "Downloading..." : "Download & Assign"}
                  </button>
                </div>
              ) : null}
              <div
                style={{
                  width: "100%",
                  display: "grid",
                  gap: "0.5rem",
                  gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                }}
              >
              {youtubeResults.map((result) => {
                const duration = formatDuration(result.duration);
                const thumbnailUrl = `https://i.ytimg.com/vi/${encodeURIComponent(
                  result.id
                )}/hqdefault.jpg`;
                const isCurrentlyAssigned =
                  !!assignedVideoId && assignedVideoId === result.id;
                const isSelected = selectedYouTubeId === result.id;
                return (
                  <Focusable
                    key={result.id}
                    onActivate={() => setSelectedYouTubeId(result.id)}
                    style={{
                      borderRadius: "0.4rem",
                      padding: "0.6rem",
                      background: isCurrentlyAssigned
                        ? "rgba(80, 190, 90, 0.22)"
                        : "rgba(255,255,255,0.05)",
                      border: isCurrentlyAssigned
                        ? "1px solid rgba(120, 230, 130, 0.75)"
                        : isSelected
                        ? "1px solid rgba(120, 180, 255, 0.85)"
                        : "1px solid transparent",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.35rem",
                    }}
                  >
                    {isSelected ? (
                      <div style={{ fontSize: "0.72rem", opacity: 0.9 }}>Selected</div>
                    ) : null}
                    <div
                      onClick={() => setSelectedYouTubeId(result.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <img
                        src={thumbnailUrl}
                        alt={result.title}
                        style={{
                          width: "100%",
                          aspectRatio: "16 / 9",
                          objectFit: "cover",
                          borderRadius: "0.35rem",
                          background: "rgba(0,0,0,0.25)",
                        }}
                      />
                    </div>
                    {isCurrentlyAssigned ? (
                      <div
                        style={{
                          display: "inline-block",
                          width: "fit-content",
                          padding: "0.15rem 0.4rem",
                          borderRadius: "0.3rem",
                          background: "rgba(120, 230, 130, 0.2)",
                          color: "#b9fbc1",
                          fontWeight: 700,
                          fontSize: "0.75rem",
                        }}
                      >
                        Currently assigned
                      </div>
                    ) : null}
                    <div style={{ fontWeight: 600 }}>{result.title}</div>
                    <div style={{ opacity: 0.8, fontSize: "0.85rem" }}>
                      {[result.uploader || "", duration].filter(Boolean).join("  |  ") ||
                        "YouTube"}
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                      <button
                        className="DialogButton"
                        onClick={() => {
                          setSelectedYouTubeId(result.id);
                          handleYouTubePreview(result);
                        }}
                        disabled={
                          previewLoadingVideoId !== null || downloadingVideoId !== null
                        }
                        style={{ minWidth: "8rem", whiteSpace: "nowrap" }}
                      >
                        {previewLoadingVideoId === result.id
                          ? "Loading..."
                          : previewingVideoId === result.id
                          ? "Stop Preview"
                          : "Play Preview"}
                      </button>
                      <button
                        className="DialogButton"
                        onClick={() => {
                          setSelectedYouTubeId(result.id);
                          handleYouTubeDownload(result);
                        }}
                        disabled={downloadingVideoId !== null}
                        style={{ minWidth: "11rem", whiteSpace: "nowrap" }}
                      >
                        {downloadingVideoId === result.id
                          ? "Downloading..."
                          : "Download & Assign"}
                      </button>
                    </div>
                  </Focusable>
                );
              })}
              {!youtubeResults.length && (
                <div style={{ opacity: 0.7, whiteSpace: "nowrap" }}>
                  No results yet. Search for a game soundtrack above.
                </div>
              )}
              </div>
            </div>
          )}
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Or, browse local files to assign from system storage">
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
              display: "grid",
              gridTemplateColumns: "1fr auto",
              width: "100%",
              gap: "0.5rem",
              alignItems: "center",
            }}
          >
            <TextField
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              style={{ width: "100%", minWidth: "20rem" }}
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

const ChangeGlobalTheme = () => {
  const [track, setTrack] = useState<GlobalTrack | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentDir, setCurrentDir] = useState("/home/deck");
  const [browser, setBrowser] = useState<DirectoryListing>({
    path: "/home/deck",
    dirs: [],
    files: [],
  });
  const [browserLoading, setBrowserLoading] = useState(true);
  const [manualPath, setManualPath] = useState("/home/deck");
  const topFocusRef = useRef<HTMLDivElement | null>(null);

  const loadTrack = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchGlobalTrack();
      setTrack(normalizeGlobalTrack(data));
    } catch (error) {
      console.error("[ThemeDeck] failed to load global track", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTrack();
  }, [loadTrack]);

  const refreshDirectory = useCallback(
    async (nextDir?: string) => {
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
    [currentDir]
  );

  useEffect(() => {
    refreshDirectory("/home/deck");
  }, []);

  useEffect(() => {
    topFocusRef.current?.focus();
  }, []);

  const saveFromPath = async (fullPath: string) => {
    try {
      const filename = fullPath.split("/").pop() || "track";
      const saved = await assignGlobalTrack(fullPath, filename);
      const normalized = normalizeGlobalTrack(saved);
      setTrack(normalized);
      latestGlobalTrackForAutoPlay = normalized;
      clearGlobalAmbientResumeSnapshot();
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
      toaster.toast({
        title: "ThemeDeck",
        body: "Saved global ambient music",
      });
    } catch (error) {
      console.error("[ThemeDeck] global save from path failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: `Unable to add file: ${getErrorMessage(error, "Unknown error")}`,
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
    try {
      await deleteGlobalTrack();
      setTrack(null);
      latestGlobalTrackForAutoPlay = null;
      clearGlobalAmbientResumeSnapshot();
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
      toaster.toast({
        title: "ThemeDeck",
        body: "Cleared global ambient music",
      });
    } catch (error) {
      console.error("[ThemeDeck] global remove failed", error);
    }
  };

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
        <div
          ref={topFocusRef}
          tabIndex={-1}
          style={{ position: "absolute", width: 0, height: 0, outline: "none" }}
        />
        <PanelSection title="ThemeDeck global / ambient track">
          <PanelSectionRow>
            {loading ? (
              <Spinner />
            ) : track ? (
              <div>
                <div style={{ fontWeight: 600 }}>{track.filename}</div>
                <div style={{ opacity: 0.8 }}>{track.path}</div>
              </div>
            ) : (
              <div>No global track selected yet.</div>
            )}
          </PanelSectionRow>
          <PanelSectionRow>
            <div
              style={{
                width: "100%",
                display: "flex",
                gap: "0.5rem",
                flexWrap: "nowrap",
                alignItems: "center",
              }}
            >
              {track ? (
                <button
                  className="DialogButton"
                  onClick={handleRemove}
                  style={{ minWidth: "8.5rem", whiteSpace: "nowrap" }}
                >
                  Remove music
                </button>
              ) : null}
              <button
                className="DialogButton"
                onClick={() => Navigation.NavigateBack()}
                style={{ minWidth: "6rem", whiteSpace: "nowrap" }}
              >
                Done
              </button>
            </div>
          </PanelSectionRow>
        </PanelSection>

        <PanelSection title="Browse local files to assign from system storage">
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
                display: "grid",
                gridTemplateColumns: "1fr auto",
                width: "100%",
                gap: "0.5rem",
                alignItems: "center",
              }}
            >
              <TextField
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                style={{ width: "100%", minWidth: "20rem" }}
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

const ChangeStoreTheme = () => {
  const [track, setTrack] = useState<StoreTrack | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentDir, setCurrentDir] = useState("/home/deck");
  const [browser, setBrowser] = useState<DirectoryListing>({
    path: "/home/deck",
    dirs: [],
    files: [],
  });
  const [browserLoading, setBrowserLoading] = useState(true);
  const [manualPath, setManualPath] = useState("/home/deck");
  const topFocusRef = useRef<HTMLDivElement | null>(null);

  const loadTrack = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchStoreTrack();
      setTrack(normalizeGlobalTrack(data));
    } catch (error) {
      console.error("[ThemeDeck] failed to load store track", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTrack();
  }, [loadTrack]);

  const refreshDirectory = useCallback(
    async (nextDir?: string) => {
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
    [currentDir]
  );

  useEffect(() => {
    refreshDirectory("/home/deck");
  }, []);

  useEffect(() => {
    topFocusRef.current?.focus();
  }, []);

  const saveFromPath = async (fullPath: string) => {
    try {
      const filename = fullPath.split("/").pop() || "track";
      const saved = await assignStoreTrack(fullPath, filename);
      const normalized = normalizeGlobalTrack(saved);
      setTrack(normalized);
      latestStoreTrackForAutoPlay = normalized;
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
      toaster.toast({
        title: "ThemeDeck",
        body: "Saved store-only music",
      });
    } catch (error) {
      console.error("[ThemeDeck] store save from path failed", error);
      toaster.toast({
        title: "ThemeDeck",
        body: `Unable to add file: ${getErrorMessage(error, "Unknown error")}`,
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
    try {
      await deleteStoreTrack();
      setTrack(null);
      latestStoreTrackForAutoPlay = null;
      window.dispatchEvent(new Event(TRACKS_UPDATED_EVENT));
      scheduleAutoPlaybackFromContext();
      toaster.toast({
        title: "ThemeDeck",
        body: "Cleared store-only music",
      });
    } catch (error) {
      console.error("[ThemeDeck] store remove failed", error);
    }
  };

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
        <div
          ref={topFocusRef}
          tabIndex={-1}
          style={{ position: "absolute", width: 0, height: 0, outline: "none" }}
        />
        <PanelSection title="ThemeDeck store-only track">
          <PanelSectionRow>
            {loading ? (
              <Spinner />
            ) : track ? (
              <div>
                <div style={{ fontWeight: 600 }}>{track.filename}</div>
                <div style={{ opacity: 0.8 }}>{track.path}</div>
              </div>
            ) : (
              <div>No store-only track selected yet.</div>
            )}
          </PanelSectionRow>
          <PanelSectionRow>
            <div
              style={{
                width: "100%",
                display: "flex",
                gap: "0.5rem",
                flexWrap: "nowrap",
                alignItems: "center",
              }}
            >
              {track ? (
                <button
                  className="DialogButton"
                  onClick={handleRemove}
                  style={{ minWidth: "8.5rem", whiteSpace: "nowrap" }}
                >
                  Remove music
                </button>
              ) : null}
              <button
                className="DialogButton"
                onClick={() => Navigation.NavigateBack()}
                style={{ minWidth: "6rem", whiteSpace: "nowrap" }}
              >
                Done
              </button>
            </div>
          </PanelSectionRow>
        </PanelSection>

        <PanelSection title="Browse local files to assign from system storage">
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
                display: "grid",
                gridTemplateColumns: "1fr auto",
                width: "100%",
                gap: "0.5rem",
                alignItems: "center",
              }}
            >
              <TextField
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                style={{ width: "100%", minWidth: "20rem" }}
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
  startAutoPlaybackCoordinator();
  const gamePatches = GAME_DETAIL_ROUTES.map((path) =>
    injectBridgeIntoRoute(path)
  );
  const contextMenuUnpatch = patchContextMenuFocus();
  routerHook.addRoute(
    "/themedeck/global",
    () => <ChangeGlobalTheme />,
    { exact: true }
  );
  routerHook.addRoute(
    "/themedeck/store",
    () => <ChangeStoreTheme />,
    { exact: true }
  );
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
      stopAutoPlaybackCoordinator();
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
      try {
        routerHook.removeRoute("/themedeck/global");
      } catch (error) {
        console.error("[ThemeDeck] remove global route failed", error);
      }
      try {
        routerHook.removeRoute("/themedeck/store");
      } catch (error) {
        console.error("[ThemeDeck] remove store route failed", error);
      }
    },
  };
});
