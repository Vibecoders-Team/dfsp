import { useEffect, useMemo, useState } from "react";
import { miniListFiles, miniVerify, normalizeMiniError, type MiniFileListItem, type MiniVerifyResponse } from "../api";
import { openWebAppLink } from "../telegram";
import { useMiniAuth } from "../auth";
import { useSearchParams } from "react-router-dom";

type VerifyState = "idle" | "loading" | "ready" | "error";

export function MiniVerifyPage() {
  const { session } = useMiniAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialId = searchParams.get("fileId") || "";

  const [fileId, setFileId] = useState(initialId);
  const [files, setFiles] = useState<MiniFileListItem[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [verifyState, setVerifyState] = useState<VerifyState>("idle");
  const [result, setResult] = useState<MiniVerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    const load = async () => {
      setLoadingFiles(true);
      try {
        const list = await miniListFiles();
        setFiles(list);
        if (!fileId && list.length > 0) {
          setFileId(list[0].id);
          setSearchParams({ fileId: list[0].id });
        }
      } catch {
        /* keep silent; verify still works with manual input */
      } finally {
        setLoadingFiles(false);
      }
    };
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  const handleVerify = async () => {
    const trimmed = fileId.trim();
    if (!trimmed) {
      setError("Укажите fileId (0x…) для сверки.");
      return;
    }
    setSearchParams(trimmed ? { fileId: trimmed } : {});
    setVerifyState("loading");
    setError(null);
    try {
      const data = await miniVerify(trimmed);
      setResult(data);
      setVerifyState("ready");
    } catch (err) {
      setResult(null);
      setVerifyState("error");
      setError(resolveVerifyError(err));
    }
  };

  const match = result?.match === true;
  const offchain = result?.offchain;
  const onchain = result?.onchain;

  const selectedOptions = useMemo(() => files.slice(0, 6), [files]);

  return (
    <div className="space-y-4">
      <section className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-2">
        <p className="text-lg font-semibold">Verify</p>
        <p className="text-sm text-slate-300">
          Сверка off-chain (БД) и on-chain метаданных: CID, keccak256 checksum, размер и mime. match=true при совпадении
          checksum.
        </p>
      </section>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={fileId}
            onChange={(e) => setFileId(e.target.value)}
            placeholder="0x… fileId"
            className="flex-1 rounded bg-slate-900 border border-slate-700 px-3 py-2 text-slate-100 placeholder:text-slate-500"
          />
          <button
            onClick={handleVerify}
            disabled={verifyState === "loading"}
            className="px-4 py-2 rounded bg-sky-500 text-slate-950 font-semibold hover:bg-sky-400 transition disabled:opacity-60"
          >
            {verifyState === "loading" ? "Проверяем…" : "Проверить"}
          </button>
        </div>
        {loadingFiles ? (
          <p className="text-xs text-slate-500">Подгружаем ваши файлы…</p>
        ) : (
          selectedOptions.length > 0 && (
            <div className="text-xs text-slate-400">
              Быстрый выбор:{" "}
              {selectedOptions.map((f, idx) => (
                <button
                  key={f.id}
                  onClick={() => {
                    setFileId(f.id);
                    setSearchParams({ fileId: f.id });
                  }}
                  className="underline hover:text-sky-300 mr-2"
                >
                  {f.name || `Файл ${idx + 1}`}
                </button>
              ))}
            </div>
          )
        )}
        {error && <div className="text-sm text-red-300 border border-red-500/50 rounded p-2">{error}</div>}
      </div>

      {verifyState === "ready" && result && (
        <div className="grid md:grid-cols-3 gap-3">
          <StatusCard match={match} onchain={onchain ?? null} offchain={offchain ?? null} />
          <MetaCard title="On-chain" meta={onchain} />
          <MetaCard title="Off-chain" meta={offchain} />
        </div>
      )}

      {verifyState === "error" && !result && (
        <div className="bg-red-900/30 border border-red-500/50 text-red-100 rounded-lg p-3 text-sm">
          {error || "Не удалось выполнить проверку."}
        </div>
      )}

      {result && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-2">
          <p className="text-sm text-slate-200">
            Детальная проверка и загрузка локального файла доступна на основном вебе.
          </p>
          <button
            onClick={() => openWebAppLink(`/verify/${fileId}`)}
            className="px-4 py-2 rounded border border-slate-600 text-slate-100 hover:border-slate-400 transition"
          >
            Открыть /verify/{truncate(fileId, 14)} на вебе
          </button>
        </div>
      )}
    </div>
  );
}

function StatusCard({
  match,
  onchain,
  offchain,
}: {
  match: boolean;
  onchain: MiniVerifyResponse["onchain"];
  offchain: MiniVerifyResponse["offchain"];
}) {
  const hint = (() => {
    if (!onchain && offchain) return "Нет on-chain записи для этого fileId.";
    if (!offchain && onchain) return "Нет off-chain данных по файлу.";
    if (!onchain && !offchain) return "Метаданные отсутствуют.";
    if (!match) return "Checksum не совпадает между on-chain и off-chain.";
    return "Checksum совпадает.";
  })();
  return (
    <div
      className={`rounded-lg border p-4 ${
        match
          ? "border-emerald-500/60 bg-emerald-900/20 text-emerald-50"
          : "border-amber-500/60 bg-amber-900/20 text-amber-50"
      }`}
    >
      <p className="text-sm uppercase tracking-wide">{match ? "match=true" : "match=false"}</p>
      <p className="text-lg font-semibold">{match ? "Checksum совпадает" : "Отличается или отсутствует запись"}</p>
      <p className="text-xs mt-1 opacity-80">{hint}</p>
      <p className="text-xs mt-1 opacity-60">Сравниваем keccak256 checksum off-chain записи с on-chain.</p>
    </div>
  );
}

function MetaCard({ title, meta }: { title: string; meta: MiniVerifyResponse["onchain"] | null | undefined }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-2">
      <p className="text-sm font-semibold text-slate-100">{title}</p>
      {meta ? (
        <div className="space-y-1 text-xs text-slate-200">
          <Row label="CID" value={meta.cid || "-"} />
          <Row label="Checksum" value={meta.checksum || "-"} monospace />
          <Row label="Size" value={formatBytes(meta.size)} />
          <Row label="MIME" value={meta.mime || "-"} />
          {meta.name && <Row label="Name" value={meta.name} />}
        </div>
      ) : (
        <p className="text-sm text-slate-500">Нет данных.</p>
      )}
    </div>
  );
}

function Row({ label, value, monospace }: { label: string; value: string; monospace?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-500">{label}</span>
      <span className={`text-right ${monospace ? "font-mono break-all" : ""}`}>{value}</span>
    </div>
  );
}

function formatBytes(size: number) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const idx = Math.min(units.length - 1, Math.floor(Math.log(size) / Math.log(1024)));
  const val = size / 1024 ** idx;
  return `${val.toFixed(val >= 10 ? 0 : 1)} ${units[idx]}`;
}

function truncate(value: string, len = 10) {
  if (!value || value.length <= len) return value;
  const half = Math.floor(len / 2);
  return `${value.slice(0, half)}…${value.slice(-half)}`;
}

function resolveVerifyError(err: unknown): string {
  const normalized = normalizeMiniError(err);
  if (normalized.status === 404 || normalized.code === "file_not_found") return "Файл не найден.";
  if (normalized.status === 400 || normalized.code === "bad_file_id") return "Некорректный fileId.";
  return normalized.message || "Ошибка проверки.";
}
