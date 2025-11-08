import type { TypedDataDomain, TypedDataField } from 'ethers';
import type { SignerAgent } from './agent';
import { ensureUnlockedOrThrow } from '../unlock';
import { ensureEOAUnlocked } from '../keychain';

export class LocalAgent implements SignerAgent {
  kind = 'local' as const;

  async getAddress(): Promise<`0x${string}`> {
    await ensureUnlockedOrThrow();
    const w = await ensureEOAUnlocked();
    return w.address as `0x${string}`;
  }

  async signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string> {
    await ensureUnlockedOrThrow();
    const w = await ensureEOAUnlocked();
    return w.signTypedData(domain, types, message as Record<string, unknown>);
  }
}
