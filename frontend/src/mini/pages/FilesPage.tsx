import { useMiniAuth } from "../auth";

export function MiniFilesPage() {
  const { session } = useMiniAuth();
  return (
    <section className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-2">
      <p className="text-lg font-semibold">Files</p>
      <p className="text-sm text-slate-300">
        Заглушка: здесь появится список файлов и интенты шаринга (MINI-3).
      </p>
      <p className="text-xs text-slate-500">Сессия активна: {Boolean(session) ? "yes" : "no"}.</p>
    </section>
  );
}
