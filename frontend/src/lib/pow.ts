// src/lib/pow.ts
import { requestPowChallenge, type PowChallenge } from "./api";
import { isAxiosError } from "axios";

export type PowToken = { challenge: string; nonce: string };

// Кэш в памяти
let cached: { token: PowToken; expiresAt: number } | null = null;

function isValidCached(): boolean {
  return !!cached && Date.now() < cached.expiresAt;
}

export async function getPowToken(): Promise<PowToken> {
  if (isValidCached()) return cached!.token;

  const ch: PowChallenge = await requestPowChallenge();

  // Запускаем воркер
  const worker = new Worker(new URL("../workers/pow.worker.ts", import.meta.url), { type: "module" });

  const nonce = await new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => {
      worker.terminate();
      reject(new Error("PoW timeout"));
    }, 15_000);

    worker.onmessage = (ev: MessageEvent<{ nonce: string }>) => {
      clearTimeout(timer);
      worker.terminate();
      resolve(ev.data.nonce);
    };
    worker.onerror = (err) => {
      clearTimeout(timer);
      worker.terminate();
      reject(err instanceof Error ? err : new Error("Worker error"));
    };

    worker.postMessage({ challenge: ch.challenge, difficulty: ch.difficulty });
  });

  const token: PowToken = { challenge: ch.challenge, nonce };
  // Кэшируем на ttl секунд
  const ttlMs = Math.max(0, (ch.ttl ?? 0) * 1000);
  cached = { token, expiresAt: Date.now() + ttlMs };

  return token;
}

/** Возвращает X-PoW строку или undefined, если PoW на бэке не включён */
export async function getOptionalPowHeader(): Promise<string | undefined> {
  try {
    const { challenge, nonce } = await getPowToken();
    return `${challenge}:${nonce}`;
  } catch (e) {
    // если бэк отвечает 404/501, просто отключаем PoW
    if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 501)) {
      return undefined;
    }
    // сетевые/другие ошибки тоже не должны блокировать шэринг
    return undefined;
  }
}