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
  private dynamicRpc: string | null = null;
  private lastError: string | null = null;
  private initializing = false;

  constructor() {
    const env: any = (import.meta as any).env ?? {};
    const cid = Number(env.VITE_CHAIN_ID || env.VITE_EXPECTED_CHAIN_ID || 31337);
    this.expectedChain = Number.isFinite(cid) && cid > 0 ? cid : 31337;
    const rpcUrl: string | undefined = env.VITE_CHAIN_RPC_URL as string | undefined;
    this.httpsRpc = (rpcUrl && rpcUrl.startsWith('https://')) ? rpcUrl : null;
  }

  private async fetchDynamicRpc(): Promise<string | null> {
    if (this.dynamicRpc) return this.dynamicRpc;
    const base = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000';
    try {
      const res = await fetch(base + '/chain/info');
      if (!res.ok) return null;
      const data = await res.json();
      const url = data.public_rpc_url;
      if (url && typeof url === 'string' && url.startsWith('https://')) {
        this.dynamicRpc = url;
        return url;
      }
    } catch (e: any) {
      this.lastError = e?.message || String(e);
    }
    return null;
  }

  private async ensureWcProvider(): Promise<BrowserProvider> {
    if (this.provider) return this.provider;
    if (this.initializing) {
      // Wait briefly for initialization to complete
      for (let i = 0; i < 20; i++) {
        if (this.provider) return this.provider;
        await new Promise(r => setTimeout(r, 50));
      }
      if (this.provider) return this.provider;
    }
    this.initializing = true;
    try {
      // Dynamic RPC fallback before init
      if (!this.httpsRpc) {
        const dyn = await this.fetchDynamicRpc();
        if (dyn) this.httpsRpc = dyn;
      }

      const env: any = (import.meta as any).env ?? {};
      const projectId = env.VITE_WALLETCONNECT_PROJECT_ID as string | undefined;
      if (!projectId) throw new Error('Missing VITE_WALLETCONNECT_PROJECT_ID');

      const mod: any = await import('@walletconnect/ethereum-provider');
      const EthereumProvider = mod.EthereumProvider ?? mod.default;

      if (this.httpsRpc && this.expectedChain) {
        this.wc = await EthereumProvider.init({
          projectId,
          chains: [this.expectedChain],
          optionalChains: [this.expectedChain],
          showQrModal: true,
          rpcMap: { [this.expectedChain]: this.httpsRpc },
        });
      } else {
        this.wc = await EthereumProvider.init({
          projectId,
          chains: [this.expectedChain],
          optionalChains: [this.expectedChain],
          showQrModal: true,
        });
      }

      if (this.wc && this.wc.enable) await this.wc.enable();
      const browserProv = new BrowserProvider(this.wc as any);
      this.provider = browserProv;

      if (this.wc && this.wc.on) {
        this.wc.on('disconnect', () => { this.provider = undefined; });
        this.wc.on('chainChanged', () => { this.provider = undefined; });
      }
      return browserProv;
    } finally {
      this.initializing = false;
    }
  }

  private async assertExpectedChain(): Promise<void> {
    if (!this.expectedChain || !this.httpsRpc) return; // skip enforcement if no https RPC
    const cid = await this.getChainId();
    if (cid !== this.expectedChain) {
      try {
        await this.switchChain(this.expectedChain);
        return;
      } catch (e: any) {
        const rpc = this.httpsRpc || this.dynamicRpc || 'RPC missing';
        throw new Error(`WalletConnect: wrong network (${cid}). Auto-switch to ${this.expectedChain} failed. RPC: ${rpc}. Add/switch the network manually in your wallet and retry. Original: ${e?.message || e}`);
      }
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
    const desired = (domain && (domain as any).chainId) ? Number((domain as any).chainId) : undefined;
    if (!desired) {
      await this.assertExpectedChain();
    }
    try {
      const wcAny = this.wc as any;
      if (desired && wcAny?.setDefaultChain) {
        try {
          await wcAny.setDefaultChain(desired);
        } catch (e) {
          console.warn('[WalletConnect] setDefaultChain failed:', e);
        }
      }
    } catch {/* ignore */}
    const signer = await prov.getSigner();
    const typesNoDomain = stripEip712Domain(types);
    console.debug('[WalletConnect] signTypedData -> desired chain', desired, 'domain.chainId', (domain as any).chainId, 'expectedChain', this.expectedChain);
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
    const env: any = (import.meta as any).env ?? {};

    const hex = '0x' + chainId.toString(16);
    try {
      if (!wcAny?.request) throw new Error('WalletConnect provider request unavailable');
      await wcAny.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
    } catch (e: any) {
      const msg = String(e?.message || '');
      if (e?.code === 4902 || /Unrecognized chain|Invalid chainId/i.test(msg)) {
        if (!this.httpsRpc) {
          throw new Error(`WalletConnect: cannot add network ${hex} — HTTPS RPC not set. Provide VITE_CHAIN_RPC_URL or backend CHAIN_PUBLIC_RPC_URL.`);
        }
        const chainName: string = env?.VITE_CHAIN_NAME || `Hardhat Local ${chainId}`;
        const explorer: string | undefined = env?.VITE_CHAIN_BLOCK_EXPLORER_URL;
        const params: any = {
          chainId: hex,
          chainName,
          rpcUrls: [this.httpsRpc],
          nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 },
        };
        if (explorer && explorer.startsWith('https://')) {
          params.blockExplorerUrls = [explorer];
        } else {
          // pass null instead of [] to satisfy wallets expecting null or non-empty array
          params.blockExplorerUrls = null;
        }
        try {
          await wcAny.request({ method: 'wallet_addEthereumChain', params: [params] });
          await wcAny.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
        } catch (addErr: any) {
          throw new Error(`WalletConnect: failed to add/switch network ${hex}. Ensure RPC '${this.httpsRpc}' reachable from device. Original: ${addErr?.message || addErr}`);
        }
      } else if (e?.code === -32603 && /eth_chainId/.test(msg)) {
        throw new Error(`WalletConnect: RPC '${this.httpsRpc}' is unreachable from wallet. Ensure ngrok forwards to http://localhost:8546 and port 8546 is published.`);
      } else if (/Invalid chainId/i.test(msg) || e?.code === -32602) {
        throw new Error(`WalletConnect: wallet rejected chainId ${hex}. Ensure RPC '${this.httpsRpc}' is HTTPS and reachable. Error: ${msg}`);
      } else {
        throw new Error(`WalletConnect: switch network error (${msg}).`);
      }
    }
    // Verify
    this.provider = undefined;
    const after = await this.getChainId();
    if (after !== chainId) {
      throw new Error(`WalletConnect: network remained ${after}, expected ${chainId}. Manual switch required in wallet UI.`);
    }
  }
}
