import React, { useState } from "react";
import { publishMyKeyCard } from "../lib/publishMyKey";
import { importKeyFromCid } from "../lib/importKeyCard";
import { getErrorMessage } from "../lib/errors";
import { ensureEOA, ensureRSA } from "../lib/keychain";

export default function Settings() {
  const [myAddr, setMyAddr] = useState<string>("");
  const [pubReady, setPubReady] = useState<boolean>(false);
  const [publishing, setPublishing] = useState(false);
  const [pubCid, setPubCid] = useState<string>("");
  const [pubUrl, setPubUrl] = useState<string>("");
  const [impInput, setImpInput] = useState<string>("");
  const [message, setMessage] = useState<string>("");

  React.useEffect(() => {
    (async () => {
      try {
        const { address } = await ensureEOA();
        await ensureRSA();
        setMyAddr(address);
        setPubReady(true);
      } catch (e) {
        setMessage(getErrorMessage(e, "Не удалось инициализировать ключи"));
      }
    })();
  }, []);

  async function onPublish() {
    try {
      setPublishing(true);
      setMessage("");
      const out = await publishMyKeyCard();
      setPubCid(out.cid);
      setPubUrl(out.url || "");
      setMessage("Публичная визитка ключа опубликована. Передайте CID/URL вашему контакту.");
    } catch (e) {
      setMessage(getErrorMessage(e, "Публикация ключа не удалась"));
    } finally {
      setPublishing(false);
    }
  }

  async function onImport() {
    try {
      setMessage("");
      if (!impInput.trim()) {
        setMessage("Укажите CID или ссылку");
        return;
      }
      const res = await importKeyFromCid(impInput.trim());
      setMessage(`Ключ импортирован: ${res.address}`);
      setImpInput("");
    } catch (e) {
      setMessage(getErrorMessage(e, "Импорт ключа не удался"));
    }
  }

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-semibold mb-4">Settings</h1>

      <section className="mb-6 p-4 border rounded">
        <h2 className="font-medium mb-2">Мой публичный ключ</h2>
        <div className="text-sm mb-2">Адрес: <code>{myAddr}</code></div>
        <button
          onClick={onPublish}
          disabled={!pubReady || publishing}
          className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
        >
          {publishing ? "Публикация…" : "Опубликовать визитку ключа"}
        </button>
        {pubCid && (
          <div className="mt-3 text-sm space-y-1">
            <div>CID: <code className="break-all">{pubCid}</code></div>
            {pubUrl && (
              <div>URL: <a href={pubUrl} target="_blank" rel="noreferrer" className="underline break-all">{pubUrl}</a></div>
            )}
          </div>
        )}
      </section>

      <section className="mb-6 p-4 border rounded">
        <h2 className="font-medium mb-2">Импорт ключа контакта</h2>
        <div className="text-sm mb-2">Вставьте CID или ссылку на визитку ключа (JSON)</div>
        <div className="flex gap-2">
          <input
            value={impInput}
            onChange={(e) => setImpInput(e.target.value)}
            placeholder="CID или https://…/ipfs/<cid>"
            className="flex-1 border rounded px-3 py-2 bg-transparent"
          />
          <button onClick={onImport} className="px-4 py-2 rounded border">Импортировать</button>
        </div>
      </section>

      {message && <div className="text-sm text-emerald-700">{message}</div>}
    </div>
  );
}

