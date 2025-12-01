import type { ReactNode } from "react";
import { useMiniAuth } from "../auth";

export function MiniAuthGate({ children }: { children: ReactNode }) {
  const { status, error, reauthenticate, loginWithTon } = useMiniAuth();

  if (status === "authenticating" || status === "idle") {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-10 text-slate-200">
        <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-sky-400" />
        <p className="text-sm">Проверяем подпись initData…</p>
        <button
          className="text-xs text-sky-300 underline hover:text-sky-200"
          onClick={() => loginWithTon()}
        >
          или войти через TON Connect
        </button>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="bg-slate-800 border border-red-500/50 rounded-lg p-4 text-sm text-slate-100 max-w-xl">
        <p className="font-semibold text-red-300 mb-1">Авторизация не прошла</p>
        <p className="text-slate-200 mb-3">{error ?? "Неизвестная ошибка"}</p>
        <div className="flex gap-2 flex-wrap">
          <button
            className="px-3 py-2 rounded bg-sky-500 text-slate-950 font-medium hover:bg-sky-400 transition"
            onClick={() => reauthenticate()}
          >
            Повторить initData
          </button>
          <button
            className="px-3 py-2 rounded border border-slate-600 text-slate-100 hover:border-slate-400 transition"
            onClick={() => loginWithTon()}
          >
            Войти через TON Connect
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
