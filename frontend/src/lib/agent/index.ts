export type { SignerAgent, AgentKind } from './agent';
export { stripEip712Domain } from './agent';
export { LocalAgent } from './local';
export { MetaMaskAgent } from './metamask';
export { WalletConnectAgent } from './walletconnect';

export function getAgent(kind: 'local' | 'metamask' | 'walletconnect') {
  if (kind === 'local') return new (require('./local').LocalAgent)();
  if (kind === 'metamask') return new (require('./metamask').MetaMaskAgent)();
  return new (require('./walletconnect').WalletConnectAgent)();
}

