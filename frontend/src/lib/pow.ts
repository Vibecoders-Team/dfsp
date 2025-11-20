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

  const cores = Math.max(2, Math.min((navigator as unknown as { hardwareConcurrency?: number }).hardwareConcurrency || 4, 8));
  const workers = Array.from({ length: cores }, () => new Worker(new URL("../workers/pow.worker.ts", import.meta.url), { type: "module" }));

  // A controller to stop all workers
  let settled = false;
  const stopAll = () => {
    if (settled) return;
    settled = true;
    for (const w of workers) {
      try {
        w.terminate();
      } catch {
        // ignore
      }
    }
  };

  const promises = workers.map((w, i) => new Promise<{ ok: boolean; v?: string }>((resolve) => {
    const onMsg = (ev: MessageEvent) => {
      try {
        const data = (ev.data as unknown) as { nonce?: string };
        if (data && typeof data.nonce === 'string') {
          resolve({ ok: true, v: data.nonce });
        } else {
          resolve({ ok: false });
        }
      } catch {
        resolve({ ok: false });
      }
    };
    const onErr = () => resolve({ ok: false });
    w.onmessage = onMsg;
    w.onerror = onErr;
    w.postMessage({ challenge: ch.challenge, difficulty: ch.difficulty, start: i, step: cores });
    return undefined as unknown as { ok: boolean; v?: string };
  }));

  // Promise.any is not available in older TS lib targets; implement a small helper
  function promiseAny<T>(ps: Promise<T>[]): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (ps.length === 0) {
      reject(new Error('No promises'));
      return;
    }
    let rejected = 0;
    for (const p of ps) {
      p.then((v) => resolve(v)).catch(() => {
        rejected += 1;
        if (rejected === ps.length) reject(new Error('All promises rejected'));
      });
    }
  });
}

  try {
    const winner = await promiseAny(promises);
    if (!winner || !winner.ok || !winner.v) throw new Error('No PoW solution');
    const nonce = winner.v as string;
    stopAll();
    const token: PowToken = { challenge: ch.challenge, nonce };
    const ttlMs = Math.max(0, (ch.ttl ?? 0) * 1000);
    cached = { token, expiresAt: Date.now() + ttlMs };
    return token;
  } catch (err) {
    stopAll();
    throw err;
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
