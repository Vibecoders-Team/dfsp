import type {ForwardTyped} from './api';
import type {SignerAgent} from '@/lib/agent';
import type {TypedDataDomain, TypedDataField} from 'ethers';

interface MaybeChainAgent extends SignerAgent {
    getChainId?: () => Promise<number | undefined>;
    switchChain?: (chainId: number) => Promise<void>;
    kind: 'local' | 'metamask' | 'walletconnect'
}

export class NetworkMismatchError extends Error {
    constructor(public readonly expected: number, public readonly actual: number) {
        super(`Network mismatch: expected chainId ${expected}, got ${actual}`);
        this.name = 'NetworkMismatchError';
    }
}

export type SignedForward = { signature: string; typedData: ForwardTyped };

export async function signForwardTyped(agent: MaybeChainAgent, td: ForwardTyped, retrySwitch = true): Promise<SignedForward> {
  const domainObj = (td.domain as unknown as Record<string, unknown>) || {};
  const desired = typeof domainObj.chainId === 'number' ? (domainObj.chainId as number) : (typeof domainObj.chainId === 'string' ? Number(domainObj.chainId) : undefined);

  // Strict network alignment for ForwardRequest (external wallets)
  if (td.primaryType === 'ForwardRequest' && agent.kind !== 'local' && desired && agent.getChainId) {
    const current = await agent.getChainId();
    if (current !== undefined && desired !== current) {
      if (retrySwitch && agent.switchChain) {
        await agent.switchChain(desired); // если switchChain бросит — пробросим наружу
      } else {
        throw new NetworkMismatchError(desired, current ?? -1);
      }
      // повторная проверка
      const after = await agent.getChainId();
      if (after !== desired) throw new NetworkMismatchError(desired, after ?? -1);
    }
  }

  const signature = await agent.signTypedData(
    td.domain as unknown as TypedDataDomain,
    td.types as Record<string, TypedDataField[]>,
    td.message as Record<string, unknown>
  );
  return { signature, typedData: td };
}
