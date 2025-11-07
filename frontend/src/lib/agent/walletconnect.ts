/* eslint-disable @typescript-eslint/no-explicit-any */
import { BrowserProvider, type TypedDataDomain, type TypedDataField } from 'ethers';
import type { SignerAgent } from './agent';
import { stripEip712Domain } from './agent';

export class WalletConnectAgent implements SignerAgent {
  kind = 'walletconnect' as const;
  private provider?: BrowserProvider;
  private wc?: { enable?: () => Promise<void>; on?: (ev: string, cb: () => void) => void; disconnect?: () => Promise<void> };
  private expectedChain: number | null = null;
  private httpsRpc: string | null = null;

  constructor() {
    const env: any = (import.meta as any).env ?? {};
    const cid = Number(env.VITE_CHAIN_ID || env.VITE_EXPECTED_CHAIN_ID || 31337);
    this.expectedChain = Number.isFinite(cid) && cid > 0 ? cid : 31337;
    const rpcUrl: string | undefined = env.VITE_CHAIN_RPC_URL as string | undefined;
    this.httpsRpc = (rpcUrl && rpcUrl.startsWith('https://')) ? rpcUrl : null;
  }

  private async ensureWcProvider(): Promise<BrowserProvider> {
    if (this.provider) return this.provider;
    const env: any = (import.meta as any).env ?? {};
    const projectId = env.VITE_WALLETCONNECT_PROJECT_ID as string | undefined;
    if (!projectId) throw new Error('Missing VITE_WALLETCONNECT_PROJECT_ID');

    const mod: any = await import('@walletconnect/ethereum-provider');
    const EthereumProvider = mod.EthereumProvider ?? mod.default;

    // Если есть HTTPS RPC для expectedChain — подключаемся строго к нему.
    if (this.httpsRpc && this.expectedChain) {
      this.wc = await EthereumProvider.init({
        projectId,
        chains: [this.expectedChain],
        optionalChains: [this.expectedChain],
        showQrModal: true,
        rpcMap: { [this.expectedChain]: this.httpsRpc },
      });
    } else {
      // Dev-fallback: нет HTTPS RPC — подключаемся к public mainnet (1) только для установления сессии.
      // Подпись EIP-712 для логина оффчейновая и домен без chainId, поэтому это допустимо.
      this.wc = await EthereumProvider.init({
        projectId,
        chains: [1],
        optionalChains: this.expectedChain ? [this.expectedChain] : [1],
        showQrModal: true,
      });
      // eslint-disable-next-line no-console
      console.warn('[WalletConnect] VITE_CHAIN_RPC_URL отсутствует или не https; авто-свитч сети отключён. Установите публичный HTTPS RPC для CHAIN_ID=', this.expectedChain);
    }

    if (this.wc && this.wc.enable) await this.wc.enable();
    const browserProv = new BrowserProvider(this.wc as any);
    this.provider = browserProv;

    if (this.wc && this.wc.on) {
      this.wc.on('disconnect', () => { this.provider = undefined; });
      this.wc.on('chainChanged', () => { this.provider = undefined; });
    }
    return browserProv;
  }

  private async assertExpectedChain(): Promise<void> {
    // Разрешаем подпись на любой сети, если нет https RPC (dev-fallback)
    if (!this.expectedChain || !this.httpsRpc) return;
    const cid = await this.getChainId();
    if (cid !== this.expectedChain) {
      throw new Error(`WalletConnect: неверная сеть (${cid}). Нажмите Switch для переключения на chainId ${this.expectedChain}.`);
    }
  }

  async getAddress(): Promise<`0x${string}`> {
    const prov = await this.ensureWcProvider();
    // не блокируем получение адреса проверкой сети
    const signer = await prov.getSigner();
    return signer.address as `0x${string}`;
  }

  async signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string> {
    const prov = await this.ensureWcProvider();
    await this.assertExpectedChain();
    const signer = await prov.getSigner();
    const typesNoDomain = stripEip712Domain(types);
    return signer.signTypedData(domain, typesNoDomain as any, message as any);
  }

  async request(method: string, params: unknown[]): Promise<unknown> {
    await this.ensureWcProvider();
    const wcAny = this.wc as any;
    if (!wcAny?.request) throw new Error('WalletConnect provider request unavailable');
    return wcAny.request({ method, params });
  }

  async getChainId(): Promise<number | undefined> {
    const prov = await this.ensureWcProvider();
    const net = await prov.getNetwork();
    return Number(net.chainId);
  }

  async disconnect(): Promise<void> {
    try { await this.wc?.disconnect?.(); } catch { /* ignore */ }
    this.provider = undefined;
  }

  async switchChain(chainId: number): Promise<void> {
    await this.ensureWcProvider();
    const current = await this.getChainId();
    if (current === chainId) return;
    const wcAny = this.wc as any;

    if (!this.httpsRpc) {
      throw new Error('WalletConnect: для автопереключения требуется публичный HTTPS RPC (VITE_CHAIN_RPC_URL=https://...). Сейчас указан http:// или переменная не задана.');
    }

    const hex = '0x' + chainId.toString(16);
    try {
      if (!wcAny?.request) throw new Error('WalletConnect provider request unavailable');
      await wcAny.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
    } catch (e: any) {
      if (e?.code === 4902) {
        const chainName: string = (import.meta as any).env?.VITE_CHAIN_NAME || `Local Hardhat (${chainId})`;
        try {
          await wcAny.request({
            method: 'wallet_addEthereumChain',
            params: [{ chainId: hex, chainName, rpcUrls: [this.httpsRpc], nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 } }],
          });
          await wcAny.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
        } catch (addErr: any) {
          throw new Error(`WalletConnect: не удалось добавить/переключить сеть (${addErr?.message || addErr}). Переключите вручную в приложении кошелька.`);
        }
      } else {
        throw new Error(`WalletConnect: ошибка переключения сети (${e?.message || e}). Переключите вручную.`);
      }
    }
    // Верификация
    this.provider = undefined; // инвалидируем
    const after = await this.getChainId();
    if (after !== chainId) {
      throw new Error(`WalletConnect: сеть после переключения = ${after}, ожидалось ${chainId}. Переключите вручную.`);
    }
  }
}
