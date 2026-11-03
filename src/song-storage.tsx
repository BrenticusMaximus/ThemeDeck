import { ComponentType, Fragment, useEffect, useRef, useState } from "react";
import { Navigation, PanelSection, PanelSectionRow, ScrollPanel, Spinner } from "@decky/ui";
import { callable } from "@decky/api";
import { getErrorMessage } from "./error-message";

type FileEntry = { id: string; name: string; path: string; category: string; bytes: number; assignments: string[] };
type Storage = { files: FileEntry[]; total_bytes: number; download_bytes: number; preview_bytes: number; unused_bytes: number; missing_assignments: string[]; busy: boolean };
type Result = { storage: Storage; freed_bytes: number; errors?: string[] };
const load = callable<[], Storage>("get_song_storage");
const remove = callable<[id: string, removeAssignments: boolean, expectedAssignments: string[]], Result>("delete_song_storage");
const cleanup = callable<[category: string], Result>("clean_song_storage");
const clearMissing = callable<[], Storage>("clear_missing_song_assignments");
export const storageSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GiB`;
};
const assignmentLabel = (key: string) => key === "__global__" ? "Global ambient" : key === "__store__" ? "Store" : `Game ${key}`;
type Action = { file?: FileEntry; category?: string; missing?: boolean; description: string };

const CompactStorageSection = ({title, children}: any) => <div style={{marginBottom: 10}}><div style={{fontSize: 14, fontWeight: 700, marginBottom: 6}}>{title}</div>{children}</div>;
const CompactStorageRow = ({children}: any) => <div style={{marginBottom: 6}}>{children}</div>;

export const SongStorage = ({ Button, onChanged, embedded = false, onClose }: { Button: ComponentType<any>; onChanged: () => void; embedded?: boolean; onClose?: () => void }) => {
  const [storage, setStorage] = useState<Storage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(30);
  const [pending, setPending] = useState<Action | null>(null);
  const actionInFlight = useRef(false);
  const confirmationRef = useRef<HTMLDivElement>(null);
  const refreshRef = useRef<HTMLDivElement>(null);
  const back = () => embedded ? onClose?.() : Navigation.NavigateBack();
  const focusButton = (element: HTMLDivElement | null) => {
    const button = element?.querySelector<HTMLElement>("button, [role='button']");
    button?.focus();
    button?.scrollIntoView({ block: "nearest" });
  };
  const refresh = async () => {
    setBusy(true); setError("");
    try { setStorage(await load()); }
    catch (error) { setError(getErrorMessage(error, "Unable to read song storage")); }
    finally { setBusy(false); }
  };
  useEffect(() => { void refresh(); }, []);
  useEffect(() => { if (pending) focusButton(confirmationRef.current); }, [pending]);
  useEffect(() => { if (storage && !busy) focusButton(refreshRef.current); }, [!!storage]);
  const confirm = async () => {
    if (!pending || actionInFlight.current) return;
    actionInFlight.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      if (pending.missing) {
        setStorage(await clearMissing());
        setNotice("Missing-file assignments cleared. No files were deleted.");
      } else {
        const result = pending.file ? await remove(pending.file.id, true, pending.file.assignments) : await cleanup(pending.category!);
        setStorage(result.storage);
        setNotice(`Freed ${storageSize(result.freed_bytes)}.${result.errors?.length ? ` Some files could not be deleted: ${result.errors.join("; ")}` : ""}`);
      }
      onChanged();
      setPending(null);
      window.setTimeout(() => focusButton(refreshRef.current), 0);
    } catch (error) { setError(getErrorMessage(error, "Unable to delete files")); }
    finally { setBusy(false); actionInFlight.current = false; }
  };
  const locked = busy || storage?.busy || !!pending;
  const entries = storage?.files.filter((file) => filter === "all" || (filter === "unused" ? !file.assignments.length : file.category === filter)) || [];
  const Container = embedded ? Fragment : ScrollPanel;
  const Section = embedded ? CompactStorageSection : PanelSection;
  const Row = embedded ? CompactStorageRow : PanelSectionRow;
  return <Container><div data-themedeck-storage={embedded ? "inline" : "page"} style={{ padding: embedded ? 12 : "48px 24px 140px", marginTop: embedded ? 8 : 0, borderRadius: 6, background: embedded ? "rgba(255,255,255,.04)" : undefined, fontSize: embedded ? 12 : undefined, overflowWrap: "anywhere" }}>
    <Section title="Song storage">
      <Row><div>
        {!embedded && <p>Manage songs downloaded by ThemeDeck and cached YouTube previews. Your own music outside these folders is not listed or deleted.</p>}
        <p style={{margin: "4px 0"}}>Deleting a file permanently removes it and clears all its assignments. Your own music outside ThemeDeck folders is excluded.</p>
        {storage && <p>Total: <strong>{storageSize(storage.total_bytes)}</strong> · Downloads: {storageSize(storage.download_bytes)} · Previews: {storageSize(storage.preview_bytes)} · Unused: {storageSize(storage.unused_bytes)}</p>}
        {storage?.busy && <p>A preview or download is in progress. Deletion is paused; refresh after it finishes.</p>}
        {error && <p role="alert" style={{ color: "#ffb4b4", whiteSpace: "pre-wrap" }}>{error}</p>}
        {notice && <p role="status">{notice}</p>}
      </div></Row>
      <Row><div ref={refreshRef} style={{ display: "flex", flexDirection: embedded ? "row" : "column", flexWrap: "wrap", gap: 6, width: "100%" }}>
        <Button disabled={busy || !!pending} onClick={refresh} onCancel={back}>Refresh storage</Button>
        <Button disabled={!!locked || !storage?.files.some((file) => file.category === "previews" && !file.assignments.length)} onClick={() => setPending({ category: "previews", description: "Delete all unused cached previews? Assigned files will be kept. You can download previews again." })} onCancel={back}>Clear cached previews</Button>
        <Button disabled={!!locked || !storage?.files.some((file) => !file.assignments.length)} onClick={() => setPending({ category: "unused", description: "Permanently delete all unassigned ThemeDeck downloads and previews? Assigned songs and your own local music will be kept." })} onCancel={back}>Delete all unused files</Button>
        {!!storage?.missing_assignments.length && <Button disabled={!!locked} onClick={() => setPending({ missing: true, description: `Clear ${storage.missing_assignments.length} assignments whose files are missing? This removes broken references without deleting any files.` })} onCancel={back}>Clear missing-file assignments ({storage.missing_assignments.length})</Button>}
        {!embedded && <Button disabled={busy} onClick={back} onCancel={back}>Back</Button>}
      </div></Row>
      {pending && <Row><div ref={confirmationRef} style={{ width: "100%" }}>
        <p role="alert">{pending.description}</p>
        <div style={{ display: "flex", flexDirection: embedded ? "row" : "column", flexWrap: "wrap", gap: 6 }}>
          <Button disabled={busy} onClick={() => { setPending(null); window.setTimeout(() => focusButton(refreshRef.current), 0); }} onCancel={() => setPending(null)}>Cancel</Button>
          <Button disabled={busy} onClick={confirm} onCancel={() => setPending(null)}>{busy ? "Working…" : pending.missing ? "Confirm clear assignments" : "Confirm permanent deletion"}</Button>
        </div>
      </div></Row>}
    </Section>
    <Section title="Files — largest first">
      <Row><div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {[["all", "All"], ["downloads", "Downloads"], ["previews", "Previews"], ["unused", "Unused"]].map(([value, label]) => <Button key={value} disabled={busy || !!pending} onClick={() => { setFilter(value); setVisibleCount(30); }} onCancel={back}>{filter === value ? "✓ " : ""}{label}</Button>)}
      </div></Row>
      <div style={embedded ? {maxHeight: 240, overflowY: "auto"} : undefined}>{busy && !storage ? <Spinner /> : entries.length === 0 ? <Row>No files in this category.</Row> : entries.slice(0, visibleCount).map((file) => <Row key={file.id}><div style={{ width: "100%", borderBottom: "1px solid #ffffff22", paddingBottom: embedded ? 6 : 12 }}>
        <div style={{ fontWeight: 600 }}>{file.name}</div>
        <div>{storageSize(file.bytes)} · {file.category === "previews" ? "Preview cache" : "Download"}</div>
        <div>{file.assignments.length ? `Assigned to: ${file.assignments.map(assignmentLabel).join(", ")}` : "Unused — no assignments"}</div>
        <Button style={{ marginTop: embedded ? 4 : 8, width: embedded ? "auto" : "100%" }} disabled={!!locked} onClick={() => setPending({ file, description: `Permanently delete “${file.name}” (${storageSize(file.bytes)})? ${file.assignments.length ? `This will also clear: ${file.assignments.map(assignmentLabel).join(", ")}.` : "This file has no assignments."}` })} onCancel={back}>Delete from disk…</Button>
      </div></Row>)}
      {entries.length > visibleCount && <Row><Button disabled={!!locked} onClick={() => setVisibleCount((count) => count + 30)} onCancel={back}>Show more files ({entries.length - visibleCount} remaining)</Button></Row>}
      </div>
    </Section>
  </div></Container>;
};

// Keep ordinary unassign non-destructive, but offer real deletion beside it
// whenever this assignment points to a ThemeDeck-owned file.
export const DeleteAssignedSong = ({ assignment, path, Button, onDeleted }: {
  assignment: string; path: string; Button: ComponentType<any>; onDeleted: () => void;
}) => {
  const [file, setFile] = useState<FileEntry | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const controlsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (confirming) {
      const cancel = controlsRef.current?.querySelector<HTMLElement>("button, [role='button']");
      cancel?.focus();
      cancel?.scrollIntoView({ block: "nearest" });
    }
  }, [confirming]);
  useEffect(() => {
    let active = true;
    setFile(null); setConfirming(false); setError("");
    void load().then((storage) => {
      if (active) setFile(storage.files.find((entry) => entry.assignments.includes(assignment)) || null);
    }).catch(() => { /* The full storage page displays scan errors. */ });
    return () => { active = false; };
  }, [assignment, path]);
  const erase = async () => {
    if (!file || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      await remove(file.id, true, file.assignments);
      onDeleted();
      setFile(null); setConfirming(false);
    } catch (error) { setError(getErrorMessage(error, "Unable to delete downloaded song")); }
    finally { inFlight.current = false; setBusy(false); }
  };
  if (!file) return null;
  return <div ref={controlsRef} style={{ width: "100%", marginTop: 8 }}>
    {confirming ? <>
      <p role="alert">Permanently delete “{file.name}” ({storageSize(file.bytes)}) from disk? This also clears: {file.assignments.map(assignmentLabel).join(", ")}. This cannot be undone.</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <Button disabled={busy} onClick={() => setConfirming(false)} onCancel={() => setConfirming(false)}>Cancel</Button>
        <Button disabled={busy} onClick={erase} onCancel={() => setConfirming(false)}>{busy ? "Deleting…" : "Confirm permanent deletion"}</Button>
      </div>
    </> : <Button onClick={() => setConfirming(true)} onCancel={() => Navigation.NavigateBack()}>Delete downloaded file from disk…</Button>}
    {error && <p role="alert" style={{ color: "#ffb4b4" }}>{error}</p>}
  </div>;
};
