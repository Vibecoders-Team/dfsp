import React, { useMemo, useState } from "react";
import { isAxiosError } from "axios";
import { fetchGranteePubKey, shareFile, ShareItem } from "../lib/api";
import { pemToArrayBuffer, arrayBufferToBase64 } from "../lib/keychain";
import { getOrCreateFileKey } from "../lib/fileKey";
import { getErrorMessage } from "../lib/errors";
import { getOptionalPowHeader } from "../lib/pow";
import { importKeyFromCid } from "../lib/importKeyCard";
import { submitMetaTx } from "../lib/api";
import { ensureEOA } from "../lib/keychain";

const addrRe = /^0x[a-fA-F0-9]{40}$/;
const isAddr = (v: string) => addrRe.test(v.trim());

type Props = {
  fileId: string;
  onClose: () => void;
  onShared: (items: ShareItem[]) => void; // после успешного POST
};

export default function ShareDialog({ fileId, onClose, onShared }: Props) {
  const [input, setInput] = useState("");
  const [grantees, setGrantees] = useState<string[]>([]);
  const [ttlDays, setTtlDays] = useState<number>(7);
  const [maxDl, setMaxDl] = useState<number>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Импорт по CID/ссылке, когда для адресата нет публичного PEM локально
  const [needPemFor, setNeedPemFor] = useState<string | null>(null);
  const [cidInput, setCidInput] = useState("");

  const canSubmit = useMemo(
    () => grantees.length > 0 && ttlDays > 0 && maxDl > 0 && !busy,
    [grantees, ttlDays, maxDl, busy]
  );

  const addGrantee = () => {
    const v = input.trim();
    if (!isAddr(v)) return setError("Неверный адрес: ожидается 0x + 40 hex символов");
    if (!grantees.includes(v)) setGrantees((prev: string[]) => [...prev, v]);
    setInput("");
    setError(null);
  };

  const removeGrantee = (a: string) => setGrantees((g: string[]) => g.filter((x: string) => x !== a));

  const onSubmit = async () => {
    try {
      setBusy(true);
      setError(null);

      // 1) K_file
      const K_file = getOrCreateFileKey(fileId); // Uint8Array(32)
      // Create a fresh ArrayBuffer to satisfy BufferSource typing (avoid SharedArrayBuffer union)
      const K_arraybuf: ArrayBuffer = (() => {
        const ab = new ArrayBuffer(K_file.byteLength);
        new Uint8Array(ab).set(K_file);
        return ab;
      })();

      // 2) encK_map: RSA-OAEP(SHA-256) для каждого адресата
      const encK_map: Record<string, string> = {};
      for (const g of grantees) {
        try {
          const pem = await fetchGranteePubKey(g); // self-share или локальный/бэкенд каталог
          const spki = pemToArrayBuffer(pem);
          const publicKey = await crypto.subtle.importKey(
            "spki",
            spki,
            { name: "RSA-OAEP", hash: "SHA-256" },
            false,
            ["encrypt"]
          );
          const ct = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, publicKey, K_arraybuf);
          encK_map[g] = arrayBufferToBase64(ct);
        } catch (e: unknown) {
          // Ключ адресата не найден локально/на бэке — предлагаем импортировать визитку по CID/ссылке
          if (e instanceof Error && e.message === "PUBLIC_PEM_NOT_FOUND") {
            setNeedPemFor(g);
            setBusy(false);
            return; // прерываем submit, ждём импорт
          }
          setError(getErrorMessage(e, "Не удалось получить ключ адресата"));
          setBusy(false);
          return;
        }
      }

      // 3) PoW: получить токен и сформировать заголовок
      let powToken = await getOptionalPowHeader();

      // 4) вызов API (с одним ретраем при 429 pow_token_*)
      let resp: { items: ShareItem[]; typedDataList?: any[] } | null = null;
      try {
        resp = await shareFile(
          fileId,
          {
            users: grantees,
            ttl_days: ttlDays,
            max_dl: maxDl,
            encK_map,
            request_id: crypto.randomUUID(),
          },
          powToken
        );
      } catch (e) {
        if (isAxiosError(e) && e.response?.status === 429) {
          const detail = (e.response?.data as any)?.detail as string | undefined;
          if (detail && detail.startsWith("pow_")) {
            powToken = await getOptionalPowHeader(true);
            resp = await shareFile(
              fileId,
              {
                users: grantees,
                ttl_days: ttlDays,
                max_dl: maxDl,
                encK_map,
                request_id: crypto.randomUUID(),
              },
              powToken
            );
          } else {
            throw e;
          }
        } else {
          throw e;
        }
      }

      // 5) Подписываем и отправляем meta-tx для grant() (если бэк вернул typedDataList)
      try {
        const tdl = resp?.typedDataList || [];
        if (tdl.length > 0) {
          const w = await ensureEOA();
          await Promise.all(
            tdl.map(async (td: any, idx: number) => {
              const sig = await w.signTypedData(td.domain, td.types, td.message);
              const reqId = crypto.randomUUID(); // независимый id для каждой grant meta-tx
              await submitMetaTx(reqId, td, sig);
            })
          );
        }
      } catch (e) {
        // Не блокируем UX шаринга, просто оставим статус "queued" до подхвата воркером
        console.warn("Grant meta-tx submit failed:", e);
      }

      onShared(resp!.items);
      onClose();
    } catch (e) {
      setError(getErrorMessage(e, "Share failed"));
    } finally {
      setBusy(false);
    }
  };

  async function doImportCid() {
    if (!needPemFor) return;
    try {
      if (!cidInput.trim()) throw new Error("Укажите CID или ссылку");
      // Импортируем визитку ключа (JSON) из /ipfs/<cid> или прямой ссылки
      await importKeyFromCid(cidInput);
      setCidInput("");
      setNeedPemFor(null);
      setError(null);
      // Повторяем сабмит — теперь ключ должен найтись в локальном каталоге
      await onSubmit();
    } catch (e) {
      setError(getErrorMessage(e, "Импорт ключа не удался"));
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-zinc-900 p-5 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-semibold">Share file</h2>
          <button
            onClick={onClose}
            className="px-2 py-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Grantees */}
        <label className="block text-sm mb-1">Grantees (0x…)</label>
        <div className="flex gap-2 mb-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => (e.key === "Enter" ? addGrantee() : undefined)}
            placeholder="0xABC…"
            className="flex-1 border rounded px-3 py-2 bg-transparent"
            aria-label="Grantee address"
          />
          <button
            onClick={addGrantee}
            className="px-3 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
          >
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2 mb-4">
          {grantees.map(a => (
            <span key={a} className="inline-flex items-center gap-2 px-2 py-1 rounded-full bg-zinc-200 dark:bg-zinc-800">
              <code className="text-xs">{a}</code>
              <button onClick={() => removeGrantee(a)} className="text-sm" aria-label={`Remove ${a}`}>✕</button>
            </span>
          ))}
        </div>

        {/* TTL / Max downloads */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <label className="block">
            <span className="text-sm">TTL (days)</span>
            <input
              type="number"
              min={1}
              value={ttlDays}
              onChange={e => setTtlDays(Math.max(1, Number(e.target.value || 0)))}
              className="w-full border rounded px-3 py-2 bg-transparent"
            />
          </label>
          <label className="block">
            <span className="text-sm">Max downloads</span>
            <input
              type="number"
              min={1}
              value={maxDl}
              onChange={e => setMaxDl(Math.max(1, Number(e.target.value || 0)))}
              className="w-full border rounded px-3 py-2 bg-transparent"
            />
          </label>
        </div>

        {/* Блок импорта, если для конкретного адреса нет публичного ключа */}
        {needPemFor && (
          <div className="mb-3 p-3 rounded-lg border border-zinc-300 dark:border-zinc-700">
            <div className="mb-2 text-sm">
              Для адреса <code className="px-1">{needPemFor}</code> ключ не найден.
              Попросите получателя отправить ссылку/QR на его ключ и вставьте сюда CID или ссылку.
            </div>
            <div className="flex gap-2">
              <input
                placeholder="CID или https://…/ipfs/<cid>"
                value={cidInput}
                onChange={(e) => setCidInput(e.target.value)}
                className="flex-1 border rounded px-3 py-2 bg-transparent"
              />
              <button
                onClick={doImportCid}
                className="px-3 py-2 rounded bg-emerald-600 text-white disabled:opacity-50"
              >
                Импортировать
              </button>
            </div>
          </div>
        )}

        {error && <div className="mb-3 text-red-600 text-sm">{error}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded border">Cancel</button>
          <button
            onClick={onSubmit}
            disabled={!canSubmit}
            className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
          >
            {busy ? "Sharing…" : "Generate keys & Share"}
          </button>
        </div>
      </div>
    </div>
  );
}
