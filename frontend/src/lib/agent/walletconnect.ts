/* eslint-disable @typescript-eslint/no-explicit-any */
import type { TypedDataDomain, TypedDataField } from 'ethers';
type BrowserProvider = import('ethers').BrowserProvider;
import type { SignerAgent } from './agent';

export class WalletConnectAgent implements SignerAgent {
  kind = 'walletconnect' as const;
  private provider?: BrowserProvider;
  private wc?: { enable?: () => Promise<void>; on?: (ev: string, cb: (...args: unknown[]) => void) => void; disconnect?: () => Promise<void>; modal?: { close?: () => void } };
  private readonly expectedChain: number | null = null;
  private httpsRpc: string | null = null;
  private dynamicRpc: string | null = null;
  private lastError: string | null = null;
  private qrShown = false;
  private initializationPromise: Promise<BrowserProvider> | null = null;
  private enabled = false;
  private displayUriCount = 0;
  private accounts: string[] = [];
  private connected = false;
  private chainEnforcementEnabled = true;

  private static GLOBAL_KEY = '__dfsp_wc_provider__';

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

  private async ensureExpectedChain(strict = false): Promise<void> {
    const expected = this.expectedChain;
    if (!this.chainEnforcementEnabled) return; // временно отключено (например во время первого login)
    if (!expected) return;
    // Ensure we have an HTTPS RPC to allow wallet_addEthereumChain if needed
    if (!this.httpsRpc) {
      const dyn = await this.fetchDynamicRpc();
      if (dyn) this.httpsRpc = dyn;
    }
    const current = await this.getChainId();
    if (current === expected) return;
    if (!this.httpsRpc) {
      const msg = `WalletConnect: HTTPS RPC URL is required to switch to chain ${expected}. Configure CHAIN_PUBLIC_RPC_URL (via ngrok_sync.sh) and retry.`;
      if (strict) throw new Error(msg);
      return;
    }
    await this.switchChain(expected);
  }

  private async ensureWcProvider(withModal = false): Promise<BrowserProvider> {
    const globalAny: any = (window as any)[WalletConnectAgent.GLOBAL_KEY];
    const wasConnectedSession = (() => { try { return sessionStorage.getItem('dfsp_wc_connected') === '1'; } catch { return false; } })();
    const wasConnectedLocal = (() => { try { return localStorage.getItem('dfsp_wc_inited') === '1'; } catch { return false; } })();
    if (!this.provider && globalAny?.wc && globalAny?.provider) {
      this.wc = globalAny.wc; this.provider = globalAny.provider as BrowserProvider; this.enabled = true; return this.provider;
    }
    if (this.provider) return this.provider;
    if (this.wc && !this.provider) {
      const { BrowserProvider } = await import('ethers');
      this.provider = new BrowserProvider(this.wc as any);
      return this.provider;
    }
    if (this.initializationPromise) return await this.initializationPromise;
    this.initializationPromise = (async () => {
       if (!this.httpsRpc) { const dyn = await this.fetchDynamicRpc(); if (dyn) this.httpsRpc = dyn; }
       const env: any = (import.meta as any).env ?? {}; const projectId = env.VITE_WALLETCONNECT_PROJECT_ID as string | undefined; if (!projectId) throw new Error('Missing VITE_WALLETCONNECT_PROJECT_ID');
       const mod: any = await import('@walletconnect/ethereum-provider'); const EthereumProvider = mod.EthereumProvider ?? mod.default;
      const shouldShowQr = withModal && !wasConnectedSession && !wasConnectedLocal && !globalAny?.provider;
      const baseConfig: any = { projectId, chains: [this.expectedChain], optionalChains: [this.expectedChain], showQrModal: shouldShowQr };
      if (shouldShowQr) baseConfig.defaultChain = this.expectedChain;
      if (this.httpsRpc && this.expectedChain) baseConfig.rpcMap = { [this.expectedChain]: this.httpsRpc };
      this.wc = await EthereumProvider.init(baseConfig); this.displayUriCount = 0;
      try { this.wc?.on?.('display_uri', () => { this.displayUriCount += 1; if (!withModal || this.displayUriCount > 1 || this.enabled || wasConnectedSession || wasConnectedLocal) setTimeout(() => { try { (this.wc as any).modal?.close?.(); } catch { /* ignore */ } }, 50); }); } catch { /* ignore */ }
      // NOTE: Do not auto-enable here to avoid background RPC polling. Enable only in connect().
      this.enabled = !!this.wc;
      this.qrShown = withModal;
      const { BrowserProvider } = await import('ethers');
      const browserProv = new BrowserProvider(this.wc as any);
      this.provider = browserProv;
      // Avoid persisting provider globally to reduce unintended reuse/polling
      //(window as any)[WalletConnectAgent.GLOBAL_KEY] = { wc: this.wc, provider: this.provider };
      if (this.wc && this.wc.on) {
        this.wc.on('disconnect', () => { this.provider = undefined; this.wc = undefined; this.qrShown = false; this.enabled = false; this.displayUriCount = 0; this.accounts = []; this.connected = false; (window as any)[WalletConnectAgent.GLOBAL_KEY] = null; try { sessionStorage.removeItem('dfsp_wc_connected'); localStorage.removeItem('dfsp_wc_inited'); } catch { /* ignore */ } try { (this.wc as any)?.modal?.close?.(); } catch { /* ignore */ } });
        try { this.wc.on('accountsChanged', (...args: unknown[]) => { const acc = Array.isArray(args[0]) ? args[0] as string[] : []; this.accounts = acc; this.connected = acc.length > 0; try { window.dispatchEvent(new CustomEvent('dfsp:wc-accounts', { detail: { accounts: acc } })); } catch { /* ignore */ } }); } catch { /* ignore */ }
        try { this.wc.on('chainChanged', (cid: any) => { let num: number | null = null; if (typeof cid === 'number') num = cid; else if (typeof cid === 'string') num = cid.startsWith('0x') ? parseInt(cid,16) : Number(cid); if (num && Number.isFinite(num)) { try { window.dispatchEvent(new CustomEvent('dfsp:wc-chain', { detail: { chainId: num } })); } catch { /* ignore */ } } }); } catch { /* ignore */ }
      }
      return browserProv;
    })();
    try { return await this.initializationPromise; } finally { this.initializationPromise = null; }
  }

  async getAddress(): Promise<`0x${string}`> {
    // Используем прямые EIP-1193 вызовы, чтобы исключить гонки сети в BrowserProvider
    await this.ensureWcProvider(); // ensure init
    const wcAny = this.wc as any;
    for (let attempt=0; attempt<3; attempt++) {
      try {
        const acc: string[] = await wcAny.request({ method: 'eth_accounts', params: [] });
        this.accounts = acc; this.connected = acc.length > 0;
        if (!this.connected) throw new Error('WalletConnect: not connected (no accounts yet). Connect wallet before continuing.');
        return acc[0] as `0x${string}`;
      } catch (e:any) {
        const msg = String(e?.message||'');
        if (/network changed:/i.test(msg) || e?.code === 'NETWORK_ERROR') {
          this.provider = undefined;
          await new Promise(r=>setTimeout(r,150*(attempt+1)));
          continue;
        }
        throw e;
      }
    }
    throw new Error('WalletConnect: unable to obtain address after network change retries');
  }

  async signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string> {
    // Для WC подписываем напрямую через eth_signTypedData_v4, избегая BrowserProvider
    await this.ensureWcProvider(false); // ensure init без модалки
    const wcAny = this.wc as any;
    // Гарантируем наличие описания EIP712Domain (wallets требуют для корректного хеша и контракт будет ожидать те же поля)
    const domainFields: TypedDataField[] = [];
    if (domain.name) domainFields.push({ name: 'name', type: 'string' });
    if ((domain as any).version) domainFields.push({ name: 'version', type: 'string' });
    if ((domain as any).chainId !== undefined) domainFields.push({ name: 'chainId', type: 'uint256' });
    if ((domain as any).verifyingContract) domainFields.push({ name: 'verifyingContract', type: 'address' });
    const hasDomainType = 'EIP712Domain' in types;
    const mergedTypes: any = { ...types };
    if (!hasDomainType) mergedTypes.EIP712Domain = domainFields;
    const primaryType = Object.keys(types).find(k => k !== 'EIP712Domain') || 'LoginChallenge';
    const typedData = { types: mergedTypes, domain, primaryType, message } as any;
    const address = await this.getAddress();
    const payload = [ address, JSON.stringify(typedData) ];
    for (let attempt=0; attempt<3; attempt++) {
      try {
        return await wcAny.request({ method: 'eth_signTypedData_v4', params: payload });
      } catch (e:any) {
        const msg = String(e?.message||'');
        if (/network changed:/i.test(msg) || e?.code === 'NETWORK_ERROR') {
          await new Promise(r=>setTimeout(r,200*(attempt+1)));
          continue;
        }
        throw e;
      }
    }
    throw new Error('WalletConnect: unable to sign typed data (v4) after retries');
  }

  async getChainId(): Promise<number | undefined> {
    await this.ensureWcProvider(false);
    const wcAny = this.wc as any;
    try {
      const hex: string = await wcAny.request({ method: 'eth_chainId', params: [] });
      return hex?.startsWith('0x') ? parseInt(hex, 16) : Number(hex);
    } catch {
      // fallback через BrowserProvider, если что-то пошло не так
      try { const net = await (this.provider as BrowserProvider).getNetwork(); return Number(net.chainId); } catch { return undefined; }
    }
  }

  async disconnect(): Promise<void> {
    try { await this.wc?.disconnect?.(); } catch { /* ignore */ }
    this.provider = undefined;
    (window as any)[WalletConnectAgent.GLOBAL_KEY] = null;
  }

  async switchChain(chainId: number): Promise<void> {
    await this.ensureWcProvider(false);
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
        if (!this.httpsRpc) throw new Error(`WalletConnect: cannot add network ${hex} — HTTPS RPC not set.`);
        const chainName: string = env?.VITE_CHAIN_NAME || `Hardhat Local ${chainId}`;
        const explorer: string | undefined = env.VITE_CHAIN_BLOCK_EXPLORER_URL;
        const explorerValid = typeof explorer === 'string' && /^(https?:\/\/\S+)$/.test(explorer);
        const params: any = { chainId: hex, chainName, rpcUrls: [this.httpsRpc], nativeCurrency: { name: 'ETH', symbol: 'ETH', decimals: 18 } };
        if (explorerValid) params.blockExplorerUrls = [explorer];
        try {
          await wcAny.request({ method: 'wallet_addEthereumChain', params: [params] });
          await wcAny.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] });
        } catch {
          const after = await this.getChainId();
          if (after !== chainId) throw new Error(`WalletConnect: network remained ${after}, expected ${chainId}. Manual switch required in wallet UI.`);
        }
      } else throw e;
    }
   }

   async connect(): Promise<void> {
     await this.ensureWcProvider(true);
     // Если уже подключено — выходим
     if (this.connected) {
       try { await this.ensureExpectedChain(false); } catch { /* ignore */ }
       return;
     }
     // Explicitly enable session only on user connect
     try { await this.wc?.enable?.(); this.enabled = true; try { sessionStorage.setItem('dfsp_wc_connected','1'); localStorage.setItem('dfsp_wc_inited','1'); } catch { /* ignore */ } } catch { /* ignore */ }
     await this.ensureExpectedChain(true);
     const start = Date.now();
     while (!this.connected && Date.now() - start < 15000) {
       try {
         const acc: string[] = await (this.wc as any)?.request?.({ method: 'eth_accounts', params: [] }) || [];
         if (acc.length > 0) { this.accounts = acc; this.connected = true; try { window.dispatchEvent(new CustomEvent('dfsp:wc-accounts', { detail: { accounts: acc } })); } catch { /* ignore */ } break; }
       } catch { /* ignore */ }
       await new Promise(r=>setTimeout(r,500));
     }
     if (!this.connected) throw new Error('WalletConnect: connection timeout (no accounts). Complete pairing in wallet and retry.');
   }

   /** Включить/выключить жесткое соблюдение expectedChain (используется при первом login для подавления network changed). */
   setChainEnforcement(enabled: boolean) {
     this.chainEnforcementEnabled = enabled;
   }
 }
