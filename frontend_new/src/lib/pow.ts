// src/lib/pow.ts
import { requestPowChallenge, type PowChallenge } from "./api";
import { isAxiosError } from "axios";

export type PowToken = { challenge: string; nonce: string };

// Кэш в памяти
let cached: { token: PowToken; expiresAt: number } | null = null;

function isValidCached(): boolean {
  return !!cached && Date.now() < cached.expiresAt;
}

export async function getPowToken(forceNew = true): Promise<PowToken> {
  if (!forceNew && isValidCached()) return cached!.token;

  const ch: PowChallenge = await requestPowChallenge();

  const cores = Math.max(2, Math.min((navigator as any).hardwareConcurrency || 4, 8));
  const workers = Array.from({ length: cores }, () => new Worker(new URL("../workers/pow.worker.ts", import.meta.url), { type: "module" }));

  // A controller to stop all workers
  let settled = false;
  const stopAll = () => {
    if (settled) return;
    settled = true;
    for (const w of workers) try { w.terminate(); } catch {}
  };

  const promises = workers.map((w, i) => new Promise<string>((resolve, reject) => {
    const onMsg = (ev: MessageEvent<{ nonce: string }>) => {
      resolve(ev.data.nonce);
    };
    const onErr = (err: any) => {
      reject(err instanceof Error ? err : new Error("Worker error"));
    };
    w.onmessage = onMsg;
    w.onerror = onErr;
    w.postMessage({ challenge: ch.challenge, difficulty: ch.difficulty, start: i, step: cores });
  }));

  const timer = new Promise<string>((_, reject) => setTimeout(() => reject(new Error("PoW timeout")), 30_000));

  try {
    const nonce = await Promise.race([Promise.any(promises), timer]);
    stopAll();
    const token: PowToken = { challenge: ch.challenge, nonce };
    const ttlMs = Math.max(0, (ch.ttl ?? 0) * 1000);
    cached = { token, expiresAt: Date.now() + ttlMs };
    return token;
  } catch (e) {
    stopAll();
    throw e;
  }
}

/**
 * Возвращает строку токена для заголовка X-PoW-Token вида "challenge.nonce".
 * Если бэк не поддерживает PoW (404/501), вернет undefined.
 * Иначе при ошибке — бросит исключение (не замалчиваем, чтобы не ловить 429 на сервере).
 */
export async function getOptionalPowHeader(forceNew = true): Promise<string | undefined> {
  try {
    const { challenge, nonce } = await getPowToken(forceNew);
    return `${challenge}.${nonce}`;
  } catch (e) {
    if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 501)) {
      return undefined;
    }
    throw e;
  }
}

