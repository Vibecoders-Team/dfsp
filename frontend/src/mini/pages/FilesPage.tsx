import { useEffect, useMemo, useState } from "react";
import {
  miniCreateIntent,
  miniListFileGrants,
  miniListFiles,
  normalizeMiniError,
  type MiniFileListItem,
  type MiniGrantItem,
  miniCreatePublicLink,
  miniListPublicLinks,
  miniRevokePublicLink,
  type MiniPublicLinkItem,
  miniRenameFile,
} from "../api";
import { useMiniAuth } from "../auth";
import { openWebAppLink } from "../telegram";
import { getOrCreateFileKey } from "@/lib/fileKey";

type GrantsState = Record<string, { loading: boolean; error: string | null; items: MiniGrantItem[] }>;
type IntentPreview = {
  id: string;
  url: string;
  ttl: number;
  action: "share" | "revoke";
  targetId: string;
  createdAt: number;
};

export function MiniFilesPage() {
  const { session, method } = useMiniAuth();
  const [files, setFiles] = useState<MiniFileListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [grants, setGrants] = useState<GrantsState>({});
  const [intent, setIntent] = useState<IntentPreview | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Public links state
  const [publicLinks, setPublicLinks] = useState<MiniPublicLinkItem[]>([]);
  const [showPublicModal, setShowPublicModal] = useState(false);
  const [creatingPublic, setCreatingPublic] = useState(false);

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await miniListFiles();
        setFiles(data);
        setSelectedId((prev) => {
          if (prev) return prev;
          return data.length > 0 ? data[0].id : null;
        });
      } catch (err) {
        setError(resolveError(err));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [session]);

  useEffect(() => {
    if (!selectedId) return;
    void loadGrants(selectedId);
    void loadPublicLinks(selectedId);
  }, [selectedId]);

  const selectedFile = useMemo(() => files.find((f) => f.id === selectedId) || null, [files, selectedId]);
  const currentGrants = selectedId ? grants[selectedId] : undefined;
  const activeIntent = useMemo(() => {
    if (!intent) return null;
    if (intent.action === "share" && selectedFile && intent.targetId === selectedFile.id) return intent;
    if (intent.action === "revoke" && currentGrants?.items.some((g) => g.capId === intent.targetId)) return intent;
    return null;
  }, [intent, selectedFile, currentGrants]);

  const loadGrants = async (fileId: string) => {
    setGrants((prev) => ({
      ...prev,
      [fileId]: { loading: true, error: null, items: prev[fileId]?.items || [] },
    }));
    try {
      const items = await miniListFileGrants(fileId);
      setGrants((prev) => ({ ...prev, [fileId]: { loading: false, error: null, items } }));
    } catch (err) {
      setGrants((prev) => ({
        ...prev,
        [fileId]: { loading: false, error: resolveError(err), items: prev[fileId]?.items || [] },
      }));
    }
  };

  const loadPublicLinks = async (fileId: string) => {
    try {
      const items = await miniListPublicLinks(fileId);
      setPublicLinks(items);
    } catch {
      setPublicLinks([]);
    }
  };

  const handleCreatePublicLink = async () => {
    if (!selectedFile) return;
    setCreatingPublic(true);
    try {
      await miniCreatePublicLink(selectedFile.id, { max_downloads: 0 });
      await loadPublicLinks(selectedFile.id);
      setShowPublicModal(false);
    } catch (err) {
      setActionError(resolveError(err));
    } finally {
      setCreatingPublic(false);
    }
  };

  const handleRevokePublicLink = async (token: string) => {
    if (!selectedFile) return;
    try {
      await miniRevokePublicLink(token);
      await loadPublicLinks(selectedFile.id);
    } catch (err) {
      setActionError(resolveError(err));
    }
  };

  const handleStartRename = (file: MiniFileListItem) => {
    setRenamingId(file.id);
    setRenameValue(file.name || "");
    setRenameError(null);
  };

  const handleCancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
    setRenameError(null);
  };

  const handleSaveRename = async () => {
    if (!renamingId || !renameValue.trim()) {
      setRenameError("Name cannot be empty");
      return;
    }
    try {
      await miniRenameFile(renamingId, renameValue.trim());
      setFiles((prev) => prev.map((f) => (f.id === renamingId ? { ...f, name: renameValue.trim() } : f)));
      setRenamingId(null);
      setRenameValue("");
      setRenameError(null);
    } catch (err) {
      setRenameError(resolveError(err));
    }
  };

  const handleShareIntent = async () => {
    if (!selectedFile) return;
    setActionError(null);
    setActionLoading("share");
    try {
      const res = await miniCreateIntent("share", {
        fileId: selectedFile.id,
        fileName: selectedFile.name,
        source: "mini",
      });
      setIntent({
        id: res.intent_id,
        url: res.url,
        ttl: res.ttl,
        action: "share",
        targetId: selectedFile.id,
        createdAt: Date.now(),
      });
    } catch (err) {
      setActionError(resolveError(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevokeIntent = async (capId: string) => {
    const fid = selectedFile?.id || selectedId;
    if (!fid) return;
    setActionError(null);
    setActionLoading(`revoke:${capId}`);
    try {
      const res = await miniCreateIntent("revoke", {
        capId,
        fileId: fid,
        source: "mini",
      });
      setIntent({
        id: res.intent_id,
        url: res.url,
        ttl: res.ttl,
        action: "revoke",
        targetId: capId,
        createdAt: Date.now(),
      });
    } catch (err) {
      setActionError(resolveError(err));
    } finally {
      setActionLoading(null);
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
  };

  const formatBytes = (size: number) => {
    if (!size) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const idx = Math.min(units.length - 1, Math.floor(Math.log(size) / Math.log(1024)));
    const val = size / 1024 ** idx;
    return `${val.toFixed(val >= 10 ? 0 : 1)} ${units[idx]}`;
  };

  const truncate = (value: string, len = 10) => {
    if (!value || value.length <= len) return value;
    const half = Math.floor(len / 2);
    return `${value.slice(0, half)}…${value.slice(-half)}`;
  };

  return (
    <div className="space-y-4">
      <section className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-2">
        <p className="text-lg font-semibold">Files</p>
        <p className="text-sm text-slate-300">
          Список ваших файлов. Шаринг и revoke выполняются через одноразовый intent и завершаются на основном вебе
          (подпись мета-транзакции).
        </p>
        <p className="text-xs text-slate-500">
          Интенты действуют ~15 минут и одноразовые: повтор даст ошибку already_used/expired.
        </p>
      </section>

      {error && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-100 rounded-lg p-3 text-sm">{error}</div>
      )}

      {method === "ton" && (
        <div className="bg-amber-900/20 border border-amber-500/50 text-amber-50 rounded-lg p-3 text-sm space-y-1">
          <p className="font-semibold">Вход через TON Connect</p>
          <p className="text-xs text-amber-100">
            Операции, требующие EVM-подписи (grant/revoke), выполняются через handoff на основной веб. Откройте ссылку
            ниже для связки EVM-адреса и подписи мета-транзакций.
          </p>
          <button
            onClick={() => openWebAppLink("/files")}
            className="mt-1 px-3 py-1 rounded border border-amber-400 text-amber-50 hover:bg-amber-500/10 transition text-xs"
          >
            Открыть основной веб
          </button>
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-3">
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="font-semibold text-sm text-slate-100">Ваши файлы</p>
            {loading && <span className="text-xs text-slate-400">обновляем…</span>}
          </div>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 rounded bg-slate-700 animate-pulse" />
              ))}
            </div>
          ) : files.length === 0 ? (
            <p className="text-sm text-slate-400">Файлы не найдены.</p>
          ) : (
            <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
              {files.map((f) => {
                const active = f.id === selectedId;
                const isRenaming = renamingId === f.id;
                return (
                  <div
                    key={f.id}
                    className={`rounded border px-3 py-2 transition ${
                      active
                        ? "bg-sky-600/20 border-sky-500 text-sky-50"
                        : "bg-slate-900/50 border-slate-700 hover:border-slate-500"
                    }`}
                  >
                    {isRenaming ? (
                      <div className="space-y-1">
                        <input
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          className="w-full px-2 py-1 rounded bg-slate-800 border border-slate-600 text-sm text-slate-100"
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveRename();
                            if (e.key === "Escape") handleCancelRename();
                          }}
                          autoFocus
                        />
                        {renameError && <p className="text-xs text-red-300">{renameError}</p>}
                        <div className="flex gap-1">
                          <button
                            onClick={handleSaveRename}
                            className="px-2 py-1 rounded bg-green-600 text-xs text-white"
                          >
                            Save
                          </button>
                          <button
                            onClick={handleCancelRename}
                            className="px-2 py-1 rounded bg-slate-600 text-xs text-white"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => setSelectedId(f.id)}
                        className="w-full text-left"
                      >
                        <div className="flex justify-between items-start">
                          <p className="font-semibold text-sm flex-1">{f.name || "Без имени"}</p>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleStartRename(f);
                            }}
                            className="text-xs text-slate-400 hover:text-slate-200 ml-2"
                          >
                            ✏️
                          </button>
                        </div>
                        <p className="text-xs text-slate-400">
                          {truncate(f.id, 14)} · {formatBytes(f.size)}
                        </p>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-3">
          <p className="font-semibold text-sm text-slate-100">Детали файла</p>
          {selectedFile ? (
            <>
              <div className="space-y-1 text-sm text-slate-200">
                <div className="flex justify-between">
                  <span className="text-slate-400">Имя</span>
                  <span className="font-medium">{selectedFile.name || "Без имени"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Размер</span>
                  <span>{formatBytes(selectedFile.size)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">CID</span>
                  <span className="text-slate-200">{truncate(selectedFile.cid, 18)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Создан</span>
                  <span>{formatDate(selectedFile.created_at)}</span>
                </div>
              </div>

              <div className="space-y-2">
                <button
                  onClick={handleShareIntent}
                  disabled={actionLoading === "share"}
                  className="w-full px-3 py-2 rounded bg-sky-500 text-slate-950 font-semibold hover:bg-sky-400 transition disabled:opacity-60"
                >
                  {actionLoading === "share" ? "Готовим intent…" : "Создать intent для шаринга"}
                </button>
                <p className="text-xs text-slate-400">
                  Откроется ссылка {`/intent/${intent?.id ?? "<id>"}`} на основном вебе, где подпишете grant.
                </p>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400">Выберите файл слева.</p>
          )}

          {actionError && <div className="text-sm text-red-300 border border-red-500/50 rounded p-2">{actionError}</div>}

          {activeIntent && <IntentCallout intent={activeIntent} openLink={openWebAppLink} />}
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-sm text-slate-100">Публичные ссылки</p>
            <button
              onClick={() => setShowPublicModal(true)}
              className="px-2 py-1 rounded bg-blue-600 text-xs text-white hover:bg-blue-700"
            >
              + Создать
            </button>
          </div>
          {!selectedFile ? (
            <p className="text-sm text-slate-400">Выберите файл слева.</p>
          ) : publicLinks.length === 0 ? (
            <p className="text-sm text-slate-400">Нет публичных ссылок.</p>
          ) : (
            <div className="space-y-2 max-h-[40vh] overflow-y-auto pr-1">
              {publicLinks.map((pl) => (
                <div key={pl.token} className="border border-slate-700 rounded p-2 bg-slate-900/40">
                  <p className="text-xs text-slate-400 break-all">Token: {truncate(pl.token, 20)}</p>
                  <p className="text-xs text-slate-400">
                    Downloads: {pl.downloads_count ?? 0}
                    {pl.policy?.max_downloads && pl.policy.max_downloads > 0
                      ? ` / ${pl.policy.max_downloads}`
                      : " / ∞"}
                  </p>
                  <div className="flex gap-1 mt-1">
                    <button
                      onClick={() => {
                        if (!selectedFile) return;
                        const K_file = getOrCreateFileKey(selectedFile.id);
                        const keyB64 = btoa(String.fromCharCode(...K_file));
                        const origin = window.location.origin;
                        const url = `${origin}/mini/public/${pl.token}#k=${encodeURIComponent(keyB64)}`;
                        navigator.clipboard.writeText(url);
                      }}
                      className="px-2 py-1 rounded bg-slate-600 text-xs text-white hover:bg-slate-500"
                    >
                      Copy
                    </button>
                    <button
                      onClick={() => handleRevokePublicLink(pl.token)}
                      className="px-2 py-1 rounded bg-red-600 text-xs text-white hover:bg-red-700"
                    >
                      Revoke
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {showPublicModal && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 max-w-sm w-full mx-4 space-y-3">
              <p className="font-semibold text-slate-100">Создать публичную ссылку</p>
              <p className="text-xs text-slate-400">
                Будет создана ссылка с безлимитными скачиваниями для файла {selectedFile?.name || ""}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleCreatePublicLink}
                  disabled={creatingPublic}
                  className="px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                >
                  {creatingPublic ? "Создаём…" : "Создать"}
                </button>
                <button
                  onClick={() => setShowPublicModal(false)}
                  className="px-3 py-2 rounded bg-slate-600 text-white hover:bg-slate-500"
                >
                  Отмена
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-sm text-slate-100">Активные гранты</p>
            {currentGrants?.loading && <span className="text-xs text-slate-400">загружаем…</span>}
          </div>
          {currentGrants?.error && (
            <div className="text-sm text-red-300 border border-red-500/50 rounded p-2">{currentGrants.error}</div>
          )}
          {!selectedFile ? (
            <p className="text-sm text-slate-400">Нет выбранного файла.</p>
          ) : currentGrants?.items?.length ? (
            <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
              {currentGrants.items.map((g) => {
                const busy = actionLoading === `revoke:${g.capId}`;
                return (
                  <div key={g.capId} className="border border-slate-700 rounded p-2 bg-slate-900/40">
                    <p className="text-sm text-slate-50 flex justify-between">
                      <span>{truncate(g.grantee, 14)}</span>
                      <span className="text-xs uppercase text-slate-400">{g.status}</span>
                    </p>
                    <p className="text-xs text-slate-400 break-all">{g.capId}</p>
                    <p className="text-xs text-slate-400">
                      DL {g.usedDownloads}/{g.maxDownloads} · до {formatDate(g.expiresAt)}
                    </p>
                    <button
                      onClick={() => handleRevokeIntent(g.capId)}
                      disabled={busy}
                      className="mt-2 w-full px-2 py-1 rounded bg-red-500 text-slate-950 font-semibold hover:bg-red-400 transition disabled:opacity-60"
                    >
                      {busy ? "Готовим revoke intent…" : "Отозвать через intent"}
                    </button>
                  </div>
                );
              })}
            </div>
          ) : currentGrants?.loading ? (
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="h-16 rounded bg-slate-700 animate-pulse" />
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Грантов пока нет.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function IntentCallout({ intent, openLink }: { intent: IntentPreview; openLink: (url: string) => void }) {
  const [remainingSec, setRemainingSec] = useState(() => calcRemaining(intent));

  useEffect(() => {
    const tick = () => setRemainingSec(calcRemaining(intent));
    const id = window.setInterval(tick, 1_000);
    tick();
    return () => clearInterval(id);
  }, [intent]);

  const expired = remainingSec <= 0;
  const minutes = Math.max(1, Math.ceil(remainingSec / 60));
  const expiresAt = new Date(intent.createdAt + intent.ttl * 1000);
  const expiresAtLabel = expiresAt.toLocaleTimeString("ru-RU", { timeStyle: "short" });
  const expiryLabel = expired
    ? "intent истёк, создайте новый"
    : `истекает через ≈${minutes} мин (до ${expiresAtLabel})`;
  return (
    <div className="border border-sky-500/40 bg-sky-900/20 rounded p-3 space-y-1 text-sm text-slate-100">
      <p className="font-semibold text-sky-200">Intent готов</p>
      <p className="text-xs text-slate-300 break-all">{intent.url}</p>
      <p className="text-xs text-slate-400">
        Действие: {intent.action} · {expiryLabel} · одноразовый.
      </p>
      <div className="flex gap-2">
        <button
          className="px-3 py-1 rounded bg-sky-500 text-slate-950 font-semibold hover:bg-sky-400 transition disabled:opacity-60"
          onClick={() => {
            if (expired) return;
            openLink(intent.url);
          }}
          disabled={expired}
        >
          Открыть
        </button>
        <button
          className="px-3 py-1 rounded border border-slate-600 text-slate-100 hover:border-slate-400 transition disabled:opacity-60"
          onClick={() => {
            if (expired) return;
            navigator.clipboard.writeText(intent.url);
          }}
          disabled={expired}
        >
          Скопировать
        </button>
      </div>
      {expired && (
        <p className="text-xs text-red-300">Intent истёк — запросите новый, они одноразовые.</p>
      )}
    </div>
  );
}

function resolveError(err: unknown): string {
  const normalized = normalizeMiniError(err);
  if (normalized.status === 410 || normalized.code === "expired") return "Intent истёк, создайте новый.";
  if (normalized.status === 409 || normalized.code === "already_used") return "Intent уже использован (одноразовый).";
  return normalized.message || "Неизвестная ошибка";
}

function calcRemaining(intent: IntentPreview): number {
  const expiresAt = intent.createdAt + intent.ttl * 1000;
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
}
