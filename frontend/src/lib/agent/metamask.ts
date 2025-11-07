/* eslint-disable @typescript-eslint/no-explicit-any */
import { BrowserProvider, type TypedDataDomain, type TypedDataField } from 'ethers';
import type { SignerAgent } from './agent';
import { stripEip712Domain } from './agent';

export class MetaMaskAgent implements SignerAgent {
  kind = 'metamask' as const;
  private provider?: BrowserProvider;
  private expectedChainId: number | null = null;

  constructor() {
    const env: any = (import.meta as any).env ?? {};
    const cid = Number(env.VITE_CHAIN_ID || env.VITE_EXPECTED_CHAIN_ID || 0);
    this.expectedChainId = Number.isFinite(cid) && cid > 0 ? cid : null;
  }

  private getEthereum(): any {
    const eth: any = (window as any).ethereum;
    if (!eth) throw new Error('MetaMask not found');
    return eth;
  }

  private async ensureProvider(): Promise<BrowserProvider> {
    if (!this.provider) {
      this.provider = new BrowserProvider(this.getEthereum());
    }
    return this.provider;
  }

  private invalidateProvider(): void {
    this.provider = undefined;
  }

  async getAddress(): Promise<`0x${string}`> {
    const p = await this.ensureProvider();
    const signer = await p.getSigner();
    return signer.address as `0x${string}`;
  }

  async getChainId(): Promise<number | undefined> {
    const p = await this.ensureProvider();
    const net = await p.getNetwork();
    return Number(net.chainId);
  }

  private async assertExpectedChain(): Promise<void> {
    if (!this.expectedChainId) return;
    const cid = await this.getChainId();
    if (cid !== this.expectedChainId) {
      throw new Error(`MetaMask: сеть ${cid} != ожидаемой ${this.expectedChainId}. Нажмите 'Switch' и повторите.`);
    }
  }

  async signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string> {
    await this.assertExpectedChain();
    const typesNoDomain = stripEip712Domain(types);

    const attempt = async (): Promise<string> => {
      const p = await this.ensureProvider();
      const signer = await p.getSigner();
      return await signer.signTypedData(domain, typesNoDomain, message as any);
    };

    for (let i = 0; i < 3; i++) {
      try {
        return await attempt();
      } catch (e) {
        const err = e as { message?: string; code?: number };
        if (err.code === 4001) throw new Error('User rejected the request');
        if (err.code === 4100) throw new Error('Unauthorized: please connect MetaMask to this site');
        if (err.code === 4902) throw new Error('Unknown chain: please add/switch network in MetaMask');
        if (err.message && /CHAIN_ID_MISMATCH/i.test(err.message)) {
            // пробуем восстановиться: инвалидируем провайдер (forge new provider), ждём и проверяем сеть
            this.invalidateProvider();
            await new Promise(r => setTimeout(r, 250 * (i + 1)));
            continue;
        }
        throw e;
      }
    }
    throw new Error('MetaMask: повторные попытки подписи завершились CHAIN_ID_MISMATCH — обновите сеть вручную и попробуйте снова');
  }

  async switchChain(chainId: number): Promise<void> {
    const eth = this.getEthereum();
    const hex = '0x' + chainId.toString(16);
    try {
      await eth.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
    } catch (e: any) {
      if (e?.code !== 4902) throw e;
      const env: any = (import.meta as any).env ?? {};
      const rpcUrl: string = env.VITE_CHAIN_RPC_URL || `${window.location.protocol}//${window.location.hostname}:8545`;
      const chainName: string = env.VITE_CHAIN_NAME || `Local Hardhat (${chainId})`;
      const params = {
        chainId: hex,
        chainName,
        rpcUrls: [rpcUrl],
        nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
        blockExplorerUrls: [] as string[],
      };
      await eth.request({ method: 'wallet_addEthereumChain', params: [params] });
      await eth.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
    }
    this.invalidateProvider();
    // Верификация сети после переключения
    for (let i = 0; i < 5; i++) {
      const cid = await this.getChainId();
      if (cid === chainId) return;
      await new Promise(r => setTimeout(r, 150));
      this.invalidateProvider();
    }
    const finalCid = await this.getChainId();
    if (finalCid !== chainId) throw new Error(`MetaMask: не удалось переключить сеть (got ${finalCid}, expected ${chainId})`);
  }
}
