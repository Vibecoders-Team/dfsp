import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  authenticateWithInitData,
  getMiniSession,
  normalizeMiniError,
  setMiniSession,
  type WebAppAuthResponse,
} from "./api";
import { readInitData, markWebAppReady } from "./telegram";

type MiniAuthStatus = "idle" | "authenticating" | "ready" | "error";

type MiniAuthContext = {
  status: MiniAuthStatus;
  session: string | null;
  error: string | null;
  expSeconds: number | null;
  reauthenticate: () => Promise<void>;
};

const MiniAuthCtx = createContext<MiniAuthContext | null>(null);

export function MiniAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<MiniAuthStatus>("idle");
  const [session, setSession] = useState<string | null>(getMiniSession());
  const [error, setError] = useState<string | null>(null);
  const [expSeconds, setExpSeconds] = useState<number | null>(null);

  const runAuth = async () => {
    setStatus("authenticating");
    setError(null);
    const initData = readInitData();
    if (!initData) {
      setStatus("error");
      setError("Отсутствует initData из Telegram WebApp.");
      return;
    }
    try {
      markWebAppReady();
      const auth: WebAppAuthResponse = await authenticateWithInitData(initData);
      setMiniSession(auth.session);
      setSession(auth.session);
      setExpSeconds(auth.exp);
      setStatus("ready");
    } catch (err) {
      setMiniSession(null);
      setSession(null);
      const message = resolveErrorMessage(err);
      setError(message);
      setStatus("error");
    }
  };

  useEffect(() => {
    if (session) {
      setStatus("ready");
      return;
    }
    void runAuth();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(
    () => ({ status, session, error, expSeconds, reauthenticate: runAuth }),
    [status, session, error, expSeconds]
  );

  return <MiniAuthCtx.Provider value={value}>{children}</MiniAuthCtx.Provider>;
}

export function useMiniAuth() {
  const ctx = useContext(MiniAuthCtx);
  if (!ctx) throw new Error("useMiniAuth must be used within MiniAuthProvider");
  return ctx;
}

function resolveErrorMessage(err: unknown): string {
  const normalized = normalizeMiniError(err);
  if (normalized.status === 403) return "Неверная подпись initData (403).";
  if (normalized.status === 401) return "Сессия истекла, обновите WebApp.";
  return normalized.message || "Неизвестная ошибка авторизации";
}
