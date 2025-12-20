/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState, useCallback, type ReactNode } from "react";
import {
  authenticateWithInitData,
  getMiniSession,
  normalizeMiniError,
  miniTonChallenge,
  miniTonLogin,
  setMiniSession,
  type WebAppAuthResponse,
} from "./api";
import { readInitData, markWebAppReady } from "./telegram";
import { getTonConnect, hexToBytes, toBase64 } from "./ton";

type MiniAuthStatus = "idle" | "authenticating" | "ready" | "error";
type AuthMethod = "telegram" | "ton" | null;

type MiniAuthContext = {
  status: MiniAuthStatus;
  session: string | null;
  method: AuthMethod;
  error: string | null;
  expSeconds: number | null;
  reauthenticate: () => Promise<void>;
  loginWithTon: () => Promise<void>;
  tonAddress: string | null;
};

const MiniAuthCtx = createContext<MiniAuthContext | null>(null);

export function MiniAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<MiniAuthStatus>("idle");
  const [session, setSession] = useState<string | null>(getMiniSession());
  const [method, setMethod] = useState<AuthMethod>(null);
  const [error, setError] = useState<string | null>(null);
  const [expSeconds, setExpSeconds] = useState<number | null>(null);
  const [tonAddress, setTonAddress] = useState<string | null>(null);

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
      setMethod("telegram");
      setStatus("ready");
    } catch (err) {
      setMiniSession(null);
      setSession(null);
      const message = resolveErrorMessage(err);
      setError(message);
      setStatus("error");
    }
  };

  const loginWithTon = useCallback(async () => {
    setStatus("authenticating");
    setError(null);
    try {
      const ton = await getTonConnect();
      if (!ton.wallet) {
        await ton.connectWallet();
      }
      const account = ton.wallet?.account;
      const pubkeyHex = account?.publicKey;
      if (!pubkeyHex) throw new Error("TON кошелёк не подключён");

      const pubB64 = toBase64(hexToBytes(pubkeyHex));
      const challenge = await miniTonChallenge(pubB64);
      const signed = await ton.signData({ type: "binary", bytes: challenge.nonce });
      const tokens = await miniTonLogin({
        challenge_id: challenge.challenge_id,
        signature: signed.signature,
        domain: signed.domain || "",
        timestamp: signed.timestamp,
        payload: { type: "binary", bytes: challenge.nonce }, // отправляем исходный nonce
        address: account?.address || "", // добавлено поле address
      });

      setMiniSession(tokens.access);
      setSession(tokens.access);
      setExpSeconds(readExp(tokens.access));
      setTonAddress(account?.address ?? null);
      setMethod("ton");
      setStatus("ready");
    } catch (err) {
      setMiniSession(null);
      setSession(null);
      setError(resolveTonError(err));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    if (session) {
      setStatus("ready");
      setExpSeconds(readExp(session));
      setMethod(detectMethod(session));
      return;
    }
    void runAuth();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(
    () => ({ status, session, method, error, expSeconds, reauthenticate: runAuth, loginWithTon, tonAddress }),
    [status, session, method, error, expSeconds, loginWithTon, tonAddress]
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
  if (normalized.status === 403) {
    if (normalized.message === "tg_not_linked" || normalized.code === "tg_not_linked") {
      return "Аккаунт Telegram не привязан к DFSP. Завершите линк в основном вебе.";
    }
    if (normalized.message === "user_not_found" || normalized.code === "user_not_found") {
      return "Пользователь для этого чата не найден.";
    }
    return "Неверная подпись initData (403).";
  }
  if (normalized.status === 401) return "Сессия истекла, обновите WebApp.";
  return normalized.message || "Неизвестная ошибка авторизации";
}

function resolveTonError(err: unknown): string {
  const normalized = normalizeMiniError(err);
  if (normalized.status === 410 || normalized.message === "challenge_expired") return "Челлендж истёк, попробуйте снова.";
  if (normalized.status === 401 || normalized.message === "bad_signature") return "Подпись TON не прошла проверку.";
  if (normalized.message === "pubkey_required" || normalized.message === "bad_pubkey") {
    return "TON кошелёк не вернул публичный ключ.";
  }
  if (err instanceof Error) return err.message;
  return normalized.message || "Не удалось войти через TON.";
}

function readExp(jwt: string | null): number | null {
  if (!jwt) return null;
  const parts = jwt.split(".");
  if (parts.length < 2) return null;
  try {
    const payload = JSON.parse(atob(parts[1]));
    if (typeof payload.exp === "number") {
      const now = Math.floor(Date.now() / 1000);
      return Math.max(0, payload.exp - now);
    }
  } catch {
    return null;
  }
  return null;
}

function detectMethod(jwt: string | null): AuthMethod {
  if (!jwt) return null;
  const parts = jwt.split(".");
  if (parts.length < 2) return null;
  try {
    const payload = JSON.parse(atob(parts[1]));
    if (payload.scope === "tg_webapp") return "telegram";
    if (payload.sub) return "ton";
  } catch {
    return null;
  }
  return null;
}
