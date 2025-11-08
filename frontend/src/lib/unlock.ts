import { isEOAUnlocked } from './keychain';

let pending: Promise<void> | null = null;
let inFlightDialog = false;

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
      try { window.dispatchEvent(new CustomEvent('dfsp:unlock-dialog')); } catch {}
    }
  });
  await pending;
  if (!isEOAUnlocked()) throw new Error('unlock_cancelled');
}
