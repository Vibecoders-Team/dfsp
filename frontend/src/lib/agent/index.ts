export type { SignerAgent, AgentKind } from './agent';
export { stripEip712Domain } from './agent';
export { LocalAgent } from './local';
export { MetaMaskAgent } from './metamask';
export { WalletConnectAgent } from './walletconnect';

import { LocalAgent } from './local';
import { MetaMaskAgent } from './metamask';
import { WalletConnectAgent } from './walletconnect';

export function getAgent(kind: 'local' | 'metamask' | 'walletconnect') {
  if (kind === 'local') return new LocalAgent();
  if (kind === 'metamask') return new MetaMaskAgent();
  return new WalletConnectAgent();
}
