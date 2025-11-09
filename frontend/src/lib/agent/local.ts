import type { TypedDataDomain, TypedDataField } from 'ethers';
import type { SignerAgent } from './agent';
import { ensureUnlockedOrThrow } from '../unlock';
import { ensureEOAUnlocked, isEOAUnlocked } from '../keychain';

function isAuthRoute(): boolean {
  try {
    const p = window.location.pathname;
    return p === '/login' || p === '/register';
  } catch { return false; }
}

export class LocalAgent implements SignerAgent {
  kind = 'local' as const;

  async getAddress(): Promise<`0x${string}`> {
    if (isAuthRoute() && !isEOAUnlocked()) {
      interface LockedError extends Error { code?: string }
      const err: LockedError = new Error('EOA locked');
      err.code = 'EOA_LOCKED';
      throw err;
    }
    await ensureUnlockedOrThrow();
    const w = await ensureEOAUnlocked();
    return w.address as `0x${string}`;
  }

  async signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string> {
    if (isAuthRoute() && !isEOAUnlocked()) {
      interface LockedError extends Error { code?: string }
      const err: LockedError = new Error('EOA locked');
      err.code = 'EOA_LOCKED';
      throw err;
    }
    await ensureUnlockedOrThrow();
    const w = await ensureEOAUnlocked();
    return w.signTypedData(domain, types, message as Record<string, unknown>);
  }
}
