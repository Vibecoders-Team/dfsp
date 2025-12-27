/* eslint-disable @typescript-eslint/no-explicit-any */
import type { TypedDataDomain, TypedDataField } from 'ethers';
type BrowserProvider = import('ethers').BrowserProvider;
import type { SignerAgent } from './agent';

// Debug helper: mask middle of string for safe logging
function maskMiddle(s: string, showStart = 4, showEnd = 4): string {
  if (!s || s.length <= showStart + showEnd + 4) return s ? '***' : '(empty)';
  return s.slice(0, showStart) + '...' + s.slice(-showEnd);
}

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
  // NEW: track display_uri timing to fail fast instead of infinite loader
  private lastDisplayUriAt: number | null = null;
  private accounts: string[] = [];
  private connected = false;
  private chainEnforcementEnabled = true;

  private static GLOBAL_KEY = '__dfsp_wc_provider__';

  // NEW: protect against double-subscription (memory leak warnings)
  private listenersBound = false;

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

  private resetLocalSessionFlags() {
    try { sessionStorage.removeItem('dfsp_wc_connected'); } catch { /* ignore */ }
    try { localStorage.removeItem('dfsp_wc_inited'); } catch { /* ignore */ }
  }

  private emitDisplayUri(uri: string) {
    try {
      window.dispatchEvent(new CustomEvent('dfsp:wc-display-uri', { detail: { uri } }));
    } catch {
      // ignore
    }
  }

  private emitCloseQr() {
    try {
      window.dispatchEvent(new CustomEvent('dfsp:wc-close-qr'));
    } catch {
      // ignore
    }
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
       const env: any = (import.meta as any).env ?? {};
       const projectId = env.VITE_WALLETCONNECT_PROJECT_ID as string | undefined;

       // DEBUG: log whether projectId is present
       console.info('[WC] projectId:', projectId ? maskMiddle(projectId) : '(MISSING!)');
       console.info('[WC] expectedChain:', this.expectedChain, 'httpsRpc:', this.httpsRpc ? maskMiddle(this.httpsRpc, 8, 8) : '(none)');

       if (!projectId) throw new Error('Missing VITE_WALLETCONNECT_PROJECT_ID');

       const mod: any = await import('@walletconnect/ethereum-provider');
       const EthereumProvider = mod.EthereumProvider ?? mod.default;

       console.info('[WC] EthereumProvider loaded, calling init with showQrModal:', withModal);

      // IMPORTANT:
      // 1) On first-time connect we *must* show QR consistently.
      // 2) Local flags (dfsp_wc_connected/dfsp_wc_inited) may become stale and prevent modal.
      // So when withModal=true we always enable the WC built-in modal.
      const shouldShowQr = withModal;

      const baseConfig: any = {
        projectId,
        chains: [this.expectedChain],
        optionalChains: [this.expectedChain],
        showQrModal: shouldShowQr,
      };
      if (shouldShowQr) baseConfig.defaultChain = this.expectedChain;
      if (this.httpsRpc && this.expectedChain) baseConfig.rpcMap = { [this.expectedChain]: this.httpsRpc };

      console.info('[WC] baseConfig:', JSON.stringify({ ...baseConfig, projectId: maskMiddle(projectId) }));

      let wcInstance: any;
      try {
        wcInstance = await EthereumProvider.init(baseConfig);
        console.info('[WC] EthereumProvider.init() succeeded');
      } catch (initErr: any) {
        console.error('[WC] EthereumProvider.init() FAILED:', initErr?.message || initErr);
        throw initErr;
      }

      this.wc = wcInstance;
      this.displayUriCount = 0;
      this.lastDisplayUriAt = null;

      // Track display_uri to detect cases when QR can't be produced (blocked WC relay, adblock, CSP, etc.)
      try {
        this.wc?.on?.('display_uri', (uri: any) => {
          console.info('[WC] display_uri event received! uri prefix:', typeof uri === 'string' ? uri.slice(0, 30) + '...' : String(uri));
          this.displayUriCount += 1;
          this.lastDisplayUriAt = Date.now();
          if (typeof uri === 'string' && uri) {
            this.emitDisplayUri(uri);
          }
          // If modal shouldn't be shown, close it quickly. (Now rarely used, but keep safe.)
          if (!withModal) {
            setTimeout(() => {
              try { (this.wc as any).modal?.close?.(); } catch { /* ignore */ }
            }, 50);
          }
        });
        console.info('[WC] display_uri listener attached');
      } catch (listenErr: any) {
        console.warn('[WC] Failed to attach display_uri listener:', listenErr?.message || listenErr);
      }

      // NOTE: Do not auto-enable here to avoid background RPC polling. Enable only in connect().
      this.enabled = !!this.wc;
      this.qrShown = withModal;
      const { BrowserProvider } = await import('ethers');
      const browserProv = new BrowserProvider(this.wc as any);
      this.provider = browserProv;
      // Avoid persisting provider globally to reduce unintended reuse/polling
      //(window as any)[WalletConnectAgent.GLOBAL_KEY] = { wc: this.wc, provider: this.provider };

      // Bind WC event listeners once per provider instance to avoid duplicated listeners.
      if (this.wc && this.wc.on && !this.listenersBound) {
        this.listenersBound = true;
        this.wc.on('disconnect', () => {
          this.provider = undefined;
          this.wc = undefined;
          this.qrShown = false;
          this.enabled = false;
          this.displayUriCount = 0;
          this.accounts = [];
          this.connected = false;
          this.listenersBound = false;
          (window as any)[WalletConnectAgent.GLOBAL_KEY] = null;
          try { sessionStorage.removeItem('dfsp_wc_connected'); localStorage.removeItem('dfsp_wc_inited'); } catch { /* ignore */ }
          try { (this.wc as any)?.modal?.close?.(); } catch { /* ignore */ }
          this.emitCloseQr();
        });
        try {
          this.wc.on('accountsChanged', (...args: unknown[]) => {
            const acc = Array.isArray(args[0]) ? args[0] as string[] : [];
            this.accounts = acc;
            this.connected = acc.length > 0;
            try { window.dispatchEvent(new CustomEvent('dfsp:wc-accounts', { detail: { accounts: acc } })); } catch { /* ignore */ }
          });
        } catch { /* ignore */ }
        try {
          this.wc.on('chainChanged', (cid: any) => {
            let num: number | null = null;
            if (typeof cid === 'number') num = cid;
            else if (typeof cid === 'string') num = cid.startsWith('0x') ? parseInt(cid,16) : Number(cid);
            if (num && Number.isFinite(num)) {
              try { window.dispatchEvent(new CustomEvent('dfsp:wc-chain', { detail: { chainId: num } })); } catch { /* ignore */ }
            }
          });
        } catch { /* ignore */ }
      }
      return browserProv;
    })();
    try { return await this.initializationPromise; } finally { this.initializationPromise = null; }
  }

  private async ensureConnected(withModal = false): Promise<void> {
    // WalletConnect EthereumProvider требует enable()/connect перед request()
    if (this.connected) return;
    // ensureWcProvider(withModal) инициализирует this.wc
    await this.ensureWcProvider(withModal);
    // Попробуем быстро определить уже существующую сессию
    try {
      const acc: string[] = await (this.wc as any)?.request?.({ method: 'eth_accounts', params: [] }) || [];
      this.accounts = acc;
      this.connected = acc.length > 0;
      if (this.connected) return;
    } catch {
      // ignore
    }
    // Если не подключены — запускаем connect() (покажет QR при необходимости)
    await this.connect();
  }

  async getAddress(): Promise<`0x${string}`> {
    // Используем прямые EIP-1193 вызовы
    await this.ensureConnected(false);
    const wcAny = this.wc as any;
    for (let attempt=0; attempt<3; attempt++) {
      try {
        const acc: string[] = await wcAny.request({ method: 'eth_accounts', params: [] });
        this.accounts = acc; this.connected = acc.length > 0;
        if (!this.connected) throw new Error('WalletConnect: not connected (no accounts yet). Connect wallet before continuing.');
        return acc[0] as `0x${string}`;
      } catch (e:any) {
        const msg = String(e?.message||'');
        if (/Please call connect\(\) before request\(\)/i.test(msg)) {
          await this.ensureConnected(true);
          continue;
        }
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
    // Для WC подписываем напрямую через eth_signTypedData_v4
    await this.ensureConnected(false);
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
        if (/Please call connect\(\) before request\(\)/i.test(msg)) {
          await this.ensureConnected(true);
          continue;
        }
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
    await this.ensureConnected(false);
    const wcAny = this.wc as any;
    try {
      const hex: string = await wcAny.request({ method: 'eth_chainId', params: [] });
      return hex?.startsWith('0x') ? parseInt(hex, 16) : Number(hex);
    } catch (e: any) {
      const msg = String(e?.message || '');
      if (/Please call connect\(\) before request\(\)/i.test(msg)) {
        await this.ensureConnected(true);
        try {
          const hex: string = await wcAny.request({ method: 'eth_chainId', params: [] });
          return hex?.startsWith('0x') ? parseInt(hex, 16) : Number(hex);
        } catch { return undefined; }
      }
      // fallback через BrowserProvider
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
     try {
      await this.ensureWcProvider(true);
    } catch (e: any) {
      // If provider init itself fails, clear stale flags so user can retry cleanly.
      this.resetLocalSessionFlags();
      throw (e instanceof Error ? e : new Error(String(e)));
    }

    // Если уже подключено — выходим
    if (this.connected) {
      try { await this.ensureExpectedChain(false); } catch { /* ignore */ }
      return;
    }

    // IMPORTANT: display_uri is emitted ONLY when enable()/connect() is called on the provider.
    // So we must call enable() first, then wait for display_uri in parallel.
    console.info('[WC] Calling enable() to trigger pairing...');

    // Start enable() - this triggers the relay connection and display_uri emission
    const enablePromise = (async () => {
      try {
        await this.wc?.enable?.();
        this.enabled = true;
        console.info('[WC] enable() completed successfully');
        // Close the built-in WC modal after successful enable
        try { (this.wc as any)?.modal?.close?.(); } catch { /* ignore */ }
        try {
          sessionStorage.setItem('dfsp_wc_connected','1');
          localStorage.setItem('dfsp_wc_inited','1');
        } catch { /* ignore */ }
      } catch (e: any) {
        console.error('[WC] enable() failed:', e?.message || e);
        // Close modal on failure too
        try { (this.wc as any)?.modal?.close?.(); } catch { /* ignore */ }
        throw e;
      }
    })();

    // Wait for display_uri (should come quickly after enable() starts)
    const uriStart = Date.now();
    while (!this.lastDisplayUriAt && Date.now() - uriStart < 12000) {
      await new Promise(r => setTimeout(r, 100));
    }

    if (!this.lastDisplayUriAt) {
      this.resetLocalSessionFlags();
      throw new Error(
        'WalletConnect: QR не удалось сгенерировать (нет события display_uri). ' +
        'Проверьте, что не блокируются соединения WalletConnect (VPN/AdBlock/Corporate proxy) и что задан VITE_WALLETCONNECT_PROJECT_ID.'
      );
    }

    // Now wait for enable() to complete (user scans QR and approves)
    try {
      await Promise.race([
        enablePromise,
        new Promise((_, rej) => setTimeout(() => rej(new Error('WalletConnect: enable() timeout')), 60000)),
      ]);
    } catch (e: any) {
      this.resetLocalSessionFlags();
      const msg = String(e?.message || e);
      throw new Error(/timeout/i.test(msg)
        ? 'WalletConnect: кошелёк не ответил на запрос подключения (таймаут). Откройте кошелёк и завершите pairing, затем повторите.'
        : 'WalletConnect: не удалось начать подключение. Проверьте кошелёк и повторите.');
    }

    await this.ensureExpectedChain(true);

    const start = Date.now();
    while (!this.connected && Date.now() - start < 15000) {
      try {
        const acc: string[] = await (this.wc as any)?.request?.({ method: 'eth_accounts', params: [] }) || [];
        if (acc.length > 0) {
          this.accounts = acc;
          this.connected = true;
          try { window.dispatchEvent(new CustomEvent('dfsp:wc-accounts', { detail: { accounts: acc } })); } catch { /* ignore */ }
          break;
        }
      } catch {
        // ignore
      }
      await new Promise(r=>setTimeout(r,500));
    }

    if (!this.connected) {
      this.resetLocalSessionFlags();
      // Close modal on failure
      try { (this.wc as any)?.modal?.close?.(); } catch { /* ignore */ }
      throw new Error('WalletConnect: connection timeout (no accounts). Complete pairing in wallet and retry.');
    }

    // Close QR modal after successful connect (helps UX).
    // Close both our custom modal and the built-in WC modal
    try { (this.wc as any)?.modal?.close?.(); } catch { /* ignore */ }
    this.emitCloseQr();
  }

  /** Включить/выключить жесткое соблюдение expectedChain (используется при первом login для подавления network changed). */
  setChainEnforcement(enabled: boolean) {
    this.chainEnforcementEnabled = enabled;
  }
}

