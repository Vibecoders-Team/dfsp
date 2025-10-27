import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ShareDialog from "../components/ShareDialog";
import { Grant, listGrants, revokeGrant } from "../lib/api";
import { getErrorMessage } from "../lib/errors";

export default function FileDetails() {
  const { fileId = "" } = useParams<{ fileId: string }>();
  const [grants, setGrants] = useState<Grant[]>([]);
  const [showShare, setShowShare] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setBusy(true);
      setError(null);
      const items = await listGrants(fileId);
      setGrants(items);
    } catch (e) {
      setError(getErrorMessage(e, "Не удалось загрузить гранты"));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (fileId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId]);

  const onRevoke = async (capId: string) => {
    try {
      await revokeGrant(capId);
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

      {error && <div className="mb-3 text-red-600 text-sm">{error}</div>}

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
              grants.map(g => (
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

      {showShare && (
        <ShareDialog
          fileId={fileId}
          onClose={() => setShowShare(false)}
          onShared={() => load()}
        />
      )}
    </div>
  );
}
