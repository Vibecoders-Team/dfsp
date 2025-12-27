import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Layout from "../Layout";
import { consumeIntent, type IntentConsumeOut } from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { isAxiosError } from "axios";

type Status = "loading" | "ready" | "error";

export default function IntentPage() {
  const { intentId = "" } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<IntentConsumeOut | null>(null);

  useEffect(() => {
    if (!intentId) {
      setError("Не передан идентификатор intent.");
      setStatus("error");
      return;
    }
    const run = async () => {
      try {
        const res = await consumeIntent(intentId);
        setData(res);
        setStatus("ready");
      } catch (err) {
        setError(describeIntentError(err));
        setStatus("error");
      }
    };
    void run();
  }, [intentId]);

  useEffect(() => {
    if (status !== "ready" || !data?.ok) return;
    const action = data.action ?? "";
    const payload = data.payload ?? {};
    persistIntentPayload(intentId, payload);

    if (action === "share" && typeof payload.fileId === "string") {
      navigate(`/files/${payload.fileId}/share?intent=${intentId}`, { replace: true });
      return;
    }

    if (action === "revoke") {
      const capId = typeof payload.capId === "string" ? payload.capId : null;
      const fileId = typeof payload.fileId === "string" ? payload.fileId : null;
      if (capId && fileId) {
        navigate(`/files/${fileId}?intent=${intentId}&revoke=${capId}`, { replace: true });
        return;
      }
    }
  }, [status, data, navigate, intentId]);

  const payloadStr = useMemo(() => {
    if (!data?.payload) return "{}";
    try {
      return JSON.stringify(data.payload, null, 2);
    } catch {
      return "{}";
    }
  }, [data]);

  return (
    <Layout>
      <div className="max-w-2xl mx-auto bg-card rounded-lg border border-border p-6 space-y-4">
        <div>
          <p className="text-sm text-muted-foreground uppercase tracking-wide mb-1">Intent</p>
          <h1 className="text-2xl font-semibold">Handoff</h1>
          <p className="text-sm text-muted-foreground mt-1">Интенты одноразовые и истекают через ~15 минут.</p>
        </div>

        {status === "loading" && (
          <div className="flex items-center gap-2 text-foreground">
            <span className="h-4 w-4 rounded-full border-b-2 border-primary animate-spin" />
            <span>Подтверждаем intent…</span>
          </div>
        )}

        {status === "error" && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            <p className="font-semibold mb-1">Не удалось использовать intent</p>
            <p>{error || "Неизвестная ошибка."}</p>
            <p className="mt-2 text-xs text-red-700">Интенты можно использовать только один раз; проверьте срок действия.</p>
          </div>
        )}

        {status === "ready" && data?.ok && (
          <div className="space-y-3">
            <div className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              <p className="font-semibold">Intent использован</p>
              <p className="text-emerald-900">
                Действие: <span className="font-mono">{data.action}</span>. Перенаправляем на нужную страницу…
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">Payload</p>
              <pre className="text-xs bg-muted text-foreground rounded p-3 overflow-auto max-h-64">{payloadStr}</pre>
            </div>
            <Link to="/files" className="inline-flex px-3 py-2 rounded bg-gray-900 text-white text-sm">
              Открыть список файлов
            </Link>
          </div>
        )}

        {status === "ready" && !data?.ok && (
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <p className="font-semibold mb-1">Intent уже использован или пустой</p>
            <p>Повторное потребление недоступно.</p>
          </div>
        )}
      </div>
    </Layout>
  );
}

function describeIntentError(err: unknown): string {
  if (isAxiosError(err)) {
    const status = err.response?.status;
    const detailRaw = (err.response?.data as { detail?: unknown } | undefined)?.detail;
    const detail = typeof detailRaw === "string" ? detailRaw : undefined;
    if (status === 404) return "Intent не найден.";
    if (status === 409 || detail === "already_used") return "Intent уже использован.";
    if (status === 410 || detail === "expired") return "Intent истёк.";
  }
  return getErrorMessage(err, "Intent недоступен");
}

function persistIntentPayload(id: string, payload: Record<string, unknown>) {
  try {
    const key = `intent:${id}`;
    sessionStorage.setItem(key, JSON.stringify(payload));
  } catch {
    /* ignore storage */
  }
}
