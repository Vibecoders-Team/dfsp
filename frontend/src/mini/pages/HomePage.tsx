import { useMiniAuth } from "../auth";
import { useEffect, useState } from "react";
import { miniApi } from "../api";

type HealthSnapshot = { ok: boolean } | null;

export function MiniHomePage() {
  const { session } = useMiniAuth();
  const [health, setHealth] = useState<HealthSnapshot>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    const probe = async () => {
      setLoading(true);
      setError(null);
      try {
        const { data } = await miniApi.get<{ ok: boolean }>("/health");
        setHealth({ ok: data.ok });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Ошибка проверки /health");
      } finally {
        setLoading(false);
      }
    };
    void probe();
  }, [session]);

  return (
    <div className="space-y-4">
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <p className="text-lg font-semibold mb-1">Привет! Это мини‑апп DFSP</p>
        <p className="text-sm text-slate-300">
          Мы валидируем initData на бэкенде и работаем через webapp‑сессию. Все запросы идут с Bearer
          JWT, полученным из <code className="text-sky-300">/tg/webapp/auth</code>.
        </p>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-2">
        <p className="font-semibold text-sm text-slate-200">Состояние сессии</p>
        <div className="text-sm text-slate-300">
          <p>JWT (обрезан): {session ? `${session.slice(0, 12)}…` : "нет"}</p>
          {loading && <p className="text-slate-400 mt-1">Проверяем /health…</p>}
          {health && <p className="text-emerald-400 mt-1">/health ok: {String(health.ok)}</p>}
          {error && <p className="text-red-400 mt-1">{error}</p>}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <Card title="Files" body="Список файлов и операции откроем здесь в MINI-3." />
        <Card title="Grants" body="Гранты и расшаривания переедут сюда в следующем таске." />
        <Card title="Verify" body="Проверка CID и сверка on/off-chain будет добавлена в MINI-4." />
        <Card title="Security" body="Неверная подпись initData даёт 403; ручка использует бэкендный HMAC." />
      </div>
    </div>
  );
}

function Card({ title, body }: { title: string; body: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <p className="font-semibold text-slate-100">{title}</p>
      <p className="text-sm text-slate-300 mt-1">{body}</p>
    </div>
  );
}
