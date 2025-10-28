import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ShareDialog from "../components/ShareDialog";
import { Grant, type ShareItem, api, prepareRevoke, submitMetaTx } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { isAxiosError } from "axios";
import { ensureEOA } from "../lib/keychain";

export default function FileDetails() {
  const { fileId = "" } = useParams<{ fileId: string }>();
  const [grants, setGrants] = useState<Grant[]>([]);
  const [pendingShared, setPendingShared] = useState<ShareItem[]>([]);
  const [showShare, setShowShare] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [grantsSupported, setGrantsSupported] = useState<boolean | null>(null);

  const load = async () => {
    try {
      setBusy(true);
      setError(null);
      // Probe backend for grants listing support; avoid spamming logs if 404
      const { data } = await api.get<{ items: Grant[] }>(`/files/${fileId}/grants`);
      setGrants(data.items);
      setGrantsSupported(true);
    } catch (e) {
      if (isAxiosError(e) && e.response?.status === 404) {
        // endpoint not implemented — disable polling and hide error
        setGrants([]);
        setGrantsSupported(false);
      } else {
        setError(getErrorMessage(e, "Не удалось загрузить гранты"));
        setGrantsSupported(true); // treat as transient error; keep polling enabled
      }
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (fileId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId]);

  // Poll only when endpoint exists
  useEffect(() => {
    if (!fileId || grantsSupported !== true) return;
    const t = setInterval(() => {
      load().catch(() => {});
    }, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, grantsSupported]);

  // Merge helper: if backend list arrives, drop from pending if present there
  const merged = React.useMemo(() => {
    const byCap = new Set(grants.map((g: Grant) => g.capId.toLowerCase()));
    const stillPending = pendingShared.filter((p: ShareItem) => !byCap.has(p.capId.toLowerCase()));
    return { grants, stillPending } as { grants: Grant[]; stillPending: ShareItem[] };
  }, [grants, pendingShared]);

  const onRevoke = async (capId: string) => {
    try {
      const prep = await prepareRevoke(capId); // {status, requestId, typedData}
      const w = await ensureEOA();
      const sig = await w.signTypedData(prep.typedData.domain as any, prep.typedData.types as any, prep.typedData.message as any);
      await submitMetaTx(prep.requestId, prep.typedData, sig);
      // optimistic reload
      await load();
    } catch (e) {
      alert(getErrorMessage(e, "Не удалось отозвать доступ"));
    }
  };

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">File details</h1>
        <button
          onClick={() => setShowShare(true)}
          className="px-4 py-2 rounded bg-blue-600 text-white"
        >
          Share
        </button>
      </div>

      {/* (опционально) карточка файла: имя, CID, размер — добавишь позже */}

      <h2 className="text-lg font-medium mt-6 mb-2">Active grants</h2>

      {grantsSupported === false && (
        <div className="mb-3 text-sm text-zinc-600">
          Список грантов на этом бэкенде пока не поддержан. Новые шаринги отобразятся ниже как "queued".
        </div>
      )}

      {error && <div className="mb-3 text-red-600 text-sm">{error}</div>}

      {/* Show newly shared (queued) items until backend reflects them */}
      {merged.stillPending.length > 0 && (
        <div className="mb-3 p-3 border rounded bg-amber-50 dark:bg-amber-900/20">
          <div className="text-sm mb-2">Recently shared (awaiting confirmation):</div>
          <ul className="text-xs space-y-1">
            {merged.stillPending.map(it => (
              <li key={it.capId} className="flex items-center gap-2">
                <span className="inline-block px-2 py-0.5 rounded border">{it.status}</span>
                <code className="break-all">{it.capId}</code>
                <span>→</span>
                <code>{it.grantee}</code>
              </li>
            ))}
          </ul>
        </div>
      )}

      {grantsSupported !== false && (
        <div className="overflow-x-auto border rounded">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-50 dark:bg-zinc-800">
              <tr>
                <th className="text-left p-2">Grantee</th>
                <th className="text-left p-2">capId</th>
                <th className="text-left p-2">Max/Used</th>
                <th className="text-left p-2">Expires</th>
                <th className="text-left p-2">Status</th>
                <th className="text-left p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {busy ? (
                <tr><td className="p-3" colSpan={6}>Loading…</td></tr>
              ) : grants.length === 0 ? (
                <tr><td className="p-3" colSpan={6}>No grants yet</td></tr>
              ) : (
                grants.map((g: Grant) => (
                  <tr key={g.capId} className="border-t">
                    <td className="p-2"><code>{g.grantee}</code></td>
                    <td className="p-2">
                      <div className="flex items-center gap-2">
                        <code className="break-all">{g.capId}</code>
                        <button
                          onClick={() => navigator.clipboard.writeText(g.capId)}
                          className="px-2 py-1 border rounded text-xs"
                        >
                          Copy
                        </button>
                        <button
                          onClick={() => navigator.clipboard.writeText(`${window.location.origin}/d/${g.capId}`)}
                          className="px-2 py-1 border rounded text-xs"
                          title="Copy download link"
                        >
                          Copy link
                        </button>
                      </div>
                    </td>
                    <td className="p-2">{g.maxDownloads}/{g.usedDownloads}</td>
                    <td className="p-2">{new Date(g.expiresAt).toLocaleString()}</td>
                    <td className="p-2">
                      <span className="px-2 py-1 rounded text-xs border">{g.status}</span>
                    </td>
                    <td className="p-2">
                      <button
                        disabled={g.status !== "confirmed" && g.status !== "pending"}
                        onClick={() => onRevoke(g.capId)}
                        className="px-3 py-1 rounded border disabled:opacity-50"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {showShare && (
        <ShareDialog
          fileId={fileId}
          onClose={() => setShowShare(false)}
          onShared={(items) => {
            setPendingShared((prev: ShareItem[]) => [...items, ...prev]);
            // optimistic reload; backend may not have the records yet, but if it does we'll merge
            load();
          }}
        />
      )}
    </div>
  );
}
