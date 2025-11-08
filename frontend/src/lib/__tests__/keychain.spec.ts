import { describe, it, expect, beforeEach } from 'vitest';
import { unlockEOA, isEOAUnlocked, lockEOA, ensureEOAUnlocked } from '../keychain';

function clearIndexedDB(): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.deleteDatabase('dfsp');
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
    req.onblocked = () => resolve();
  });
}

describe('EOA lock/unlock', () => {
  beforeEach(async () => {
    lockEOA();
    await clearIndexedDB();
  });

  it('creates new EOA on first unlock and locks/unlocks correctly', async () => {
    expect(isEOAUnlocked()).toBe(false);
    const addrHex = await unlockEOA('test-password-123');
    expect(addrHex).toMatch(/^0x[0-9a-fA-F]{64}$/);
    expect(isEOAUnlocked()).toBe(true);
    lockEOA();
    expect(isEOAUnlocked()).toBe(false);
  });

  it('ensureEOAUnlocked throws when locked and no password', async () => {
    await expect(ensureEOAUnlocked(undefined as any)).rejects.toThrow(/password/i);
  });
});

