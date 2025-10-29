// src/pages/DownloadCap.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ACCESS_TOKEN_KEY } from "../lib/api";
import { ensureRSA, ensureEOA } from "../lib/keychain";
import { fetchDownload, fetchGrantByCapId, type GrantStatus, submitMetaTx } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { getOptionalPowHeader } from "../lib/pow";
import { isAxiosError } from "axios";

const IPFS_GATEWAY = import.meta.env.VITE_IPFS_PUBLIC_GATEWAY ?? "http://localhost:8080";

// локальный helper: base64 -> Uint8Array
function b64ToU8(b64: string): Uint8Array {
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8;
}

export default function DownloadCap() {
  const { capId = "" } = useParams<{ capId: string }>();
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState<number>(0); // 0..100
  const [phase, setPhase] = useState<"idle"|"fetch"|"decrypt"|"download"|"saving"|"done">("idle");
  const [grant, setGrant] = useState<GrantStatus | null>(null);
  const pollingRef = useRef<number | null>(null);

  // --- DEV BYPASS state ---
  const [devIpfsPath, setDevIpfsPath] = useState("");
  const [devFilename, setDevFilename] = useState("");

  const hasJwt = useMemo(() => !!localStorage.getItem(ACCESS_TOKEN_KEY), []);

  // Пуллим статус гранта каждые 3с
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const g = await fetchGrantByCapId(capId);
        if (!cancelled) setGrant(g);
      } catch { /* молча */ }
      finally {
        // повторим через 3с, пока не терминальный статус
        if (!cancelled) {
          const s = grant?.status;
          const terminal = s === "revoked" || s === "expired" || s === "exhausted";
          pollingRef.current = window.setTimeout(poll, terminal ? 8000 : 3000);
        }
      }
    }
    poll();
    return () => {
      cancelled = true;
      if (pollingRef.current) window.clearTimeout(pollingRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capId]);

  async function startDownload() {
    try {
      setErr("");
      setProgress(0);
      setPhase("fetch");

      let powHeader = await getOptionalPowHeader();
      let encK: string;
      let ipfsPath: string;
      let requestId: string | undefined;
      let typedData: any | undefined;
      try {
        const res = await fetchDownload(capId, powHeader);
        encK = res.encK; ipfsPath = res.ipfsPath; requestId = res.requestId; typedData = res.typedData as any;
      } catch (e) {
        if (isAxiosError(e) && e.response?.status === 429) {
          const detail = (e.response?.data as any)?.detail as string | undefined;
          if (detail && detail.startsWith("pow_")) {
            // получим новый токен и попробуем ещё раз
            powHeader = await getOptionalPowHeader(true);
            const res2 = await fetchDownload(capId, powHeader);
            encK = res2.encK; ipfsPath = res2.ipfsPath; requestId = res2.requestId; typedData = res2.typedData as any;
          } else {
            throw e;
          }
        } else {
          throw e;
        }
      }

      // Асинхронно подпишем и отправим useOnce, чтобы зафиксировать использование на чейне
      if (requestId && typedData) {
        (async () => {
          try {
            const w = await ensureEOA();
            const sig = await w.signTypedData(typedData.domain, typedData.types, typedData.message);
            await submitMetaTx(requestId, typedData, sig);
          } catch {
            // ignore errors here; UI подтянет фактический статус позже
          }
        })();
      }

      setPhase("decrypt");
      // Расшифруем симметричный ключ K_file своей приваткой RSA-OAEP
      const { privateKey } = await ensureRSA();
      const encBytes = b64ToU8(encK);
      // важный момент: у ensureRSA приватка под RSA-PSS (sign), но формат ключа тот же.
      // Для расшифровки бэк должен был генерить RSA-OAEP-совместимый публичный ключ.
      // На MVP допускаем, что приватка подходит. Если нет — бэк/ключи нужно выровнять.
      const K_file_buf = await crypto.subtle.decrypt({ name: "RSA-OAEP" }, privateKey as CryptoKey, encBytes)
        .catch(() => new ArrayBuffer(32)); // на MVP позволяем продолжить даже без расшифровки

      // Скачивание данных через IPFS-шлюз
      setPhase("download");
      const base = IPFS_GATEWAY.replace(/\/+$/, "");
      const path = ipfsPath.startsWith("/") ? ipfsPath : `/${ipfsPath}`;
      const url = `${base}${path}`;

      const resp = await fetch(url);
      if (!resp.ok || !resp.body) {
        throw new Error(`Download failed: ${resp.status} ${resp.statusText}`);
      }

      // Стримим с прогрессом (если есть Content-Length)
      const total = Number(resp.headers.get("Content-Length") ?? 0);
      const reader = resp.body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          received += value.length;
          if (total > 0) setProgress(Math.round((received / total) * 100));
        }
      }

      // MVP: пока отдаём как есть (без AES-GCM), когда появится шифрование — расшифруем чанки K_file'ом
      // (K_file_buf получен выше; оставляем задел на FE-4)
      setPhase("saving");
      const blob = new Blob(chunks);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = capId; // имя файла — временно capId; позже можно спросить у API метаданные/имя
      a.click();
      URL.revokeObjectURL(a.href);

      setProgress(100);
      setPhase("done");
    } catch (e) {
      setErr(getErrorMessage(e, "Не удалось скачать файл"));
      setPhase("idle");
      setProgress(0);
    }
  }

  // DEV BYPASS: прямое скачивание по введённому ipfsPath (без capId/бэка)
  async function startDownloadDev() {
    try {
      setErr("");
      setProgress(0);
      setPhase("download");

      const base = IPFS_GATEWAY.replace(/\/+$/, "");
      const path = devIpfsPath.startsWith("/") ? devIpfsPath : `/${devIpfsPath}`;
      const url = `${base}${path}`;

      const resp = await fetch(url);
      if (!resp.ok || !resp.body) throw new Error(`Download failed: ${resp.status} ${resp.statusText}`);

      const total = Number(resp.headers.get("Content-Length") ?? 0);
      const reader = resp.body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          received += value.length;
          if (total > 0) setProgress(Math.round((received / total) * 100));
        }
      }

      setPhase("saving");
      const blob = new Blob(chunks);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = devFilename || capId || "download";
      a.click();
      URL.revokeObjectURL(a.href);

      setProgress(100);
      setPhase("done");
    } catch (e) {
      setErr(getErrorMessage(e, "Не удалось скачать файл (dev)"));
      setPhase("idle");
      setProgress(0);
    }
  }

  // Сообщения для типичных ошибок 403/429
  const humanGrant = useMemo(() => {
    if (!err) return "";
    if (/403/.test(err) || /forbidden/i.test(err)) {
      // попытка подсказки причины
      const s = grant?.status;
      if (s === "revoked") return "Доступ отозван владельцем.";
      if (s === "expired") return "Срок действия ссылки истёк.";
      if (s === "exhausted") return "Лимит скачиваний исчерпан.";
      return "Доступ запрещён.";
    }
    if (/429/.test(err)) return "Требуется PoW или превышена квота. Попробуйте ещё раз.";
    return "";
  }, [err, grant]);

  return (
    <div className="container">
      <h1>Download</h1>
      <p><code>capId:</code> {capId}</p>

      {!hasJwt ? (
        <div className="card" style={{marginTop: 16}}>
          <p>Чтобы скачать файл, войдите в систему.</p>
          <Link to="/login" className="btn">Войти</Link>
        </div>
      ) : (
        <div className="card" style={{marginTop: 16}}>
          <div style={{display: "flex", gap: 12, alignItems: "center"}}>
            <button onClick={startDownload} disabled={phase !== "idle" && phase !== "done"}>
              {phase === "idle" && "Download"}
              {phase === "fetch" && "Fetching…"}
              {phase === "decrypt" && "Decrypting key…"}
              {phase === "download" && (progress ? `Downloading… ${progress}%` : "Downloading…")}
              {phase === "saving" && "Saving…"}
              {phase === "done" && "Download again"}
            </button>
            {progress > 0 && phase !== "done" && (
              <span style={{opacity: 0.85}}>{progress}%</span>
            )}
          </div>

          {err && <p style={{color: "crimson", marginTop: 10}}>{err}</p>}
          {humanGrant && <p style={{color: "orange"}}>{humanGrant}</p>}

          {grant && (
            <div style={{marginTop: 16, fontSize: 14, opacity: 0.9}}>
              <div><b>Status:</b> {grant.status}</div>
              <div><b>Used/Max:</b> {grant.usedDownloads}/{grant.maxDownloads}</div>
              {grant.expiresAt && <div><b>Expires:</b> {new Date(grant.expiresAt).toLocaleString()}</div>}
            </div>
          )}

          {import.meta.env.VITE_DEV_BYPASS === "1" && (
            <div style={{marginTop: 20, paddingTop: 12, borderTop: "1px dashed #666"}}>
              <div style={{fontWeight: 600, marginBottom: 8}}>Dev bypass (без бэкенда)</div>
              <div style={{display: "grid", gap: 8}}>
                <input
                  placeholder="ipfsPath (например, /ipfs/Qm... или /ipns/...)"
                  value={devIpfsPath}
                  onChange={e => setDevIpfsPath(e.target.value)}
                  className="border rounded px-3 py-2 bg-transparent"
                />
                <input
                  placeholder="Имя файла (опционально)"
                  value={devFilename}
                  onChange={e => setDevFilename(e.target.value)}
                  className="border rounded px-3 py-2 bg-transparent"
                />
                <button onClick={startDownloadDev} disabled={!devIpfsPath}>
                  Download (dev)
                </button>
                <div style={{fontSize: 12, opacity: 0.8}}>
                  Загрузка через {IPFS_GATEWAY}. Шифрование пропускаем — цель проверить поток/прогресс/сохранение.
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
