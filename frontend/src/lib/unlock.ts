import { isEOAUnlocked } from './keychain';

let pending: Promise<void> | null = null;
let inFlightDialog = false;

// Ephemeral storage for last unlock password (clears automatically)
let lastUnlockPassword: string | null = null;
let lastUnlockTimer: number | null = null;
const LAST_UNLOCK_TTL_MS = 5 * 60 * 1000; // 5 minutes

export function rememberLastUnlockPassword(pwd: string) {
  lastUnlockPassword = pwd;
  if (lastUnlockTimer) clearTimeout(lastUnlockTimer);
  lastUnlockTimer = window.setTimeout(() => { lastUnlockPassword = null; lastUnlockTimer = null; }, LAST_UNLOCK_TTL_MS);
}
export function consumeLastUnlockPassword(): string | null {
  const p = lastUnlockPassword;
  lastUnlockPassword = null;
  if (lastUnlockTimer) { clearTimeout(lastUnlockTimer); lastUnlockTimer = null; }
  return p;
}
export function getLastUnlockPassword(): string | null { return lastUnlockPassword; }

export async function ensureUnlockedOrThrow(): Promise<void> {
  if (isEOAUnlocked()) return;
  if (pending) { await pending; if (!isEOAUnlocked()) throw new Error('unlock_cancelled'); return; }
  pending = new Promise<void>((resolve) => {
    const onUnlocked = () => { cleanup(); resolve(); };
    const onCancel = () => { cleanup(); resolve(); };
    const cleanup = () => {
      window.removeEventListener('dfsp:unlocked', onUnlocked);
      window.removeEventListener('dfsp:unlock-cancel', onCancel);
      pending = null; inFlightDialog = false;
    };
    window.addEventListener('dfsp:unlocked', onUnlocked, { once: true });
    window.addEventListener('dfsp:unlock-cancel', onCancel, { once: true });
    if (!inFlightDialog) {
      inFlightDialog = true;
      try { window.dispatchEvent(new CustomEvent('dfsp:unlock-dialog')); } catch (e) { console.debug('dispatch unlock-dialog failed', e); }
    }
  });
  await pending;
  if (!isEOAUnlocked()) throw new Error('unlock_cancelled');
}
