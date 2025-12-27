import type { TypedDataDomain, TypedDataField } from 'ethers';
import type { SignerAgent } from './agent';

/**
 * TonAgent is a placeholder for TON Connect users.
 *
 * TON-only users cannot perform EVM signatures (EIP-712 typed data signing)
 * because:
 * 1. TON uses Ed25519 signatures, EVM uses secp256k1 (ECDSA)
 * 2. The MinimalForwarder contract verifies ECDSA signatures
 * 3. The derived ETH address from TON pubkey has no corresponding private key
 *
 * Users must link an EVM wallet (MetaMask/WalletConnect) for share/revoke/useOnce operations.
 */
export class TonAgent implements SignerAgent {
  kind = 'ton' as const;
  private tonAddress: string;
  private derivedEthAddress: string;

  constructor() {
    // Get stored addresses from localStorage
    this.tonAddress = localStorage.getItem('dfsp_ton_address') || '';
    this.derivedEthAddress = localStorage.getItem('dfsp_address') || '';
  }

  async getAddress(): Promise<`0x${string}`> {
    if (!this.derivedEthAddress) {
      throw new Error('TON address not found. Please re-login with TON Connect.');
    }
    return this.derivedEthAddress as `0x${string}`;
  }

  async signTypedData(
    _domain: TypedDataDomain,
    _types: Record<string, TypedDataField[]>,
    _message: Record<string, unknown>
  ): Promise<string> {
    throw new Error(
      'On-chain operations require an EVM wallet. ' +
      'TON signatures cannot be verified by Ethereum smart contracts. ' +
      'Please link MetaMask or WalletConnect to use share/revoke features.'
    );
  }

  getTonAddress(): string {
    return this.tonAddress;
  }
}

