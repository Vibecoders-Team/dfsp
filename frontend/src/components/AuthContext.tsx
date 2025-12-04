/* eslint-disable react-refresh/only-export-components */
/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { createContext, useState, useEffect, ReactNode } from 'react';
import { hasEOA, ensureEOA, ensureRSA, createBackupBlob, restoreFromBackup, type LoginMessage, LOGIN_TYPES as KC_LOGIN_TYPES, LOGIN_DOMAIN as KC_LOGIN_DOMAIN, unlockEOA, type RestoreResult } from '@/lib/keychain';
import { postChallenge, postLogin, postRegister, postTonChallenge, postTonLogin, ACCESS_TOKEN_KEY, type RegisterPayload, type TypedLoginData, type TonSignPayload } from '@/lib/api';
import { ethers, type TypedDataDomain, type TypedDataField } from 'ethers';
import { getAgent } from '@/lib/agent/manager';
import { ensureUnlockedOrThrow } from '@/lib/unlock';
import { setSelectedAgentKind } from '@/lib/agent/manager';
import { deriveEthFromTonPub, getTonConnect, hexToBytes, toBase64 } from '@/lib/tonconnect';

const LOGIN_DOMAIN: TypedDataDomain = KC_LOGIN_DOMAIN;
const LOGIN_TYPES: Record<string, TypedDataField[]> = KC_LOGIN_TYPES;
const EXPECTED_CHAIN_ID = Number((import.meta as any).env?.VITE_CHAIN_ID || 0);
const ADDRESS_KEY = 'dfsp_address';
const TON_ADDRESS_KEY = 'dfsp_ton_address';
const AUTH_METHOD_KEY = 'dfsp_auth_method';
const SESSION_GEN_KEY = 'SESSION_GEN';
function bumpSessionGen() {
  try { localStorage.setItem(SESSION_GEN_KEY, crypto.randomUUID()); } catch { /* ignore */ }
}

interface User {
  address: string;
  displayName?: string;
  hasBackup: boolean;
  authMethod?: 'eoa' | 'ton';
  tonAddress?: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (opts?: { unlockPassword?: string }) => Promise<void>;
  loginWithTon: () => Promise<void>;
  register: (password: string, confirmPassword: string, displayName?: string) => Promise<{ backupData: Blob }>;
  logout: () => void;
  restoreAccount: (file: File, password: string) => Promise<RestoreResult>;
  updateBackupStatus: (hasBackup: boolean) => void;
}

export type { AuthContextType };
export const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Helper to convert types for ethers v6
function toEthersTypes(src: Record<string, readonly ethers.TypedDataField[]>): Record<string, ethers.TypedDataField[]> {
  return Object.fromEntries(
    Object.entries(src)
      .filter(([k]) => k !== "EIP712Domain")
      .map(([k, arr]) => [k, Array.from(arr)])
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check for existing session
    const checkAuth = async () => {
      try {
        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
        if (!token) { setIsLoading(false); return; }
        const address = localStorage.getItem(ADDRESS_KEY) || null;
        const storedName = localStorage.getItem('dfsp_display_name');
        const authMethod = (localStorage.getItem(AUTH_METHOD_KEY) as 'eoa' | 'ton' | null) || 'eoa';
        const tonAddress = localStorage.getItem(TON_ADDRESS_KEY) || undefined;
        const backup = authMethod === 'ton' ? false : await hasEOA();
        if (address) {
          setUser({ address, displayName: storedName || undefined, hasBackup: backup, authMethod, tonAddress });
        }
        // ensure session gen exists
        const gen = localStorage.getItem(SESSION_GEN_KEY);
        if (!gen) bumpSessionGen();
      } catch (error) {
        console.error('Auth check failed (non-fatal):', error);
      } finally {
        setIsLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (opts?: { unlockPassword?: string }) => {
       const challenge = await postChallenge();
       const agent = await getAgent();
       if (agent.kind === 'local') {
         const hasLocal = await hasEOA();
         if (!hasLocal) {
           throw new Error('Local key not found. Switch to MetaMask/WalletConnect or restore a full backup.');
         }
         if (opts?.unlockPassword) {
           try { await unlockEOA(opts.unlockPassword); } catch {/* fallback to dialog */}
         }
       }
       // For local agent: prompt unlock dialog and wait before proceeding
       if (agent.kind === 'local') {
         try { await ensureUnlockedOrThrow(); } catch { throw new Error('Unlock cancelled'); }
       }
       // Network handling: MetaMask strict, WalletConnect lenient with short stabilization
       if (EXPECTED_CHAIN_ID && agent.getChainId) {
         const current0 = await agent.getChainId();
         if (agent.kind === 'metamask') {
           if (current0 !== EXPECTED_CHAIN_ID) {
             if ((agent as any).switchChain) {
               try { await (agent as any).switchChain(EXPECTED_CHAIN_ID); }
               catch { throw new Error(`Wrong network (${current0}). Please switch to ${EXPECTED_CHAIN_ID} and retry.`); }
             } else {
               throw new Error(`Wrong network (${current0}). Please switch to ${EXPECTED_CHAIN_ID} and retry.`);
             }
           }
         } else if (agent.kind === 'walletconnect') {
           // temporarily disable chain enforcement inside agent to avoid network-changed race
           if ((agent as any).setChainEnforcement) { try { (agent as any).setChainEnforcement(false); } catch { /* ignore */ } }
           let stabilized = current0;
           for (let i=0; i<6; i++) { // ~1.2s max
             if (stabilized === EXPECTED_CHAIN_ID) break;
             await new Promise(r=>setTimeout(r,200));
             try { stabilized = await agent.getChainId() ?? stabilized; } catch { /* ignore */ }
           }
         }
       }
       const address = await agent.getAddress();
       const message: LoginMessage = { address, nonce: challenge.nonce as `0x${string}` };
       const curCid = agent.getChainId ? await agent.getChainId() : undefined;
       // For walletconnect do NOT inject chainId to domain to avoid add/switch requirement during simple login
       const domain: TypedDataDomain = (agent.kind === 'metamask' && curCid)
         ? { ...LOGIN_DOMAIN, chainId: curCid }
         : LOGIN_DOMAIN;
       const TYPES: Record<string, TypedDataField[]> = toEthersTypes(LOGIN_TYPES);
       let signature: string;
       try {
         signature = await agent.signTypedData(domain, TYPES, message as unknown as Record<string, unknown>);
       } catch (e: any) {
         const code = e?.code ?? e?.error?.code;
         const msg: string = e?.message || '';
         if (code === 4001 || code === 'ACTION_REJECTED' || /user rejected/i.test(msg)) {
           throw new Error('Signature request was cancelled');
         }
         throw new Error('Failed to sign the login challenge');
       } finally {
         if ((agent as any).setChainEnforcement) { try { (agent as any).setChainEnforcement(true); } catch { /* ignore */ } }
       }
       const recovered = ethers.verifyTypedData(domain, TYPES, message, signature);
       if (recovered.toLowerCase() !== address.toLowerCase()) {
          throw new Error(`Signature verification failed: recovered ${recovered} ≠ ${address}`);
       }
       const payload = {
          challenge_id: challenge.challenge_id,
          eth_address: address,
          typed_data: {
           domain,
            types: TYPES,
            primaryType: "LoginChallenge" as const,
            message,
          } satisfies TypedLoginData,
          signature,
       };
       const tokens = await postLogin(payload);
       localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
       localStorage.setItem('REFRESH_TOKEN', tokens.refresh);
       localStorage.setItem(ADDRESS_KEY, address);
       localStorage.setItem(AUTH_METHOD_KEY, 'eoa');
       localStorage.removeItem(TON_ADDRESS_KEY);
       bumpSessionGen();
       const storedName = localStorage.getItem('dfsp_display_name');
       const backup = await hasEOA();
       setUser({ address, displayName: storedName || undefined, hasBackup: backup, authMethod: 'eoa' });
   };

  const loginWithTon = async () => {
    const ton = getTonConnect();
    if (!ton.wallet) {
      await ton.connectWallet();
    }
    const account = ton.wallet?.account;
    const pubkeyHex = account?.publicKey;
    const tonAddress = account?.address;
    if (!pubkeyHex || !tonAddress) {
      throw new Error('TON wallet not connected');
    }

    const pubB64 = toBase64(hexToBytes(pubkeyHex));
    const challenge = await postTonChallenge(pubB64);
    // mark signing stage for UI consumers
    try { setSelectedAgentKind('local'); } catch { /* ignore */ }
    const signed = await ton.signData({ type: "binary", bytes: challenge.nonce });
    const payload: TonSignPayload =
      (signed as { payload?: TonSignPayload })?.payload || { type: "binary", bytes: challenge.nonce };
    const ts =
      typeof (signed as { timestamp?: number }).timestamp === "number"
        ? (signed as { timestamp: number }).timestamp
        : Math.floor(Date.now() / 1000);

    const tokens = await postTonLogin({
      challenge_id: challenge.challenge_id,
      signature: (signed as { signature: string }).signature,
      domain: (signed as { domain?: string }).domain || "",
      timestamp: ts,
      payload,
      address: tonAddress,
    });

    const derivedEth = deriveEthFromTonPub(pubkeyHex);
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
    localStorage.setItem('REFRESH_TOKEN', tokens.refresh);
    localStorage.setItem(ADDRESS_KEY, derivedEth);
    localStorage.setItem(TON_ADDRESS_KEY, tonAddress);
    localStorage.setItem(AUTH_METHOD_KEY, 'ton');
    bumpSessionGen();
    setUser({ address: derivedEth, displayName: 'TON user', hasBackup: false, authMethod: 'ton', tonAddress });
  };

  const register = async (
    password: string,
    confirmPassword: string,
    displayName?: string
  ): Promise<{ backupData: Blob }> => {
       if (password !== confirmPassword) throw new Error('Passwords do not match');
       if (password.length < 8) {
         throw new Error('Password must be at least 8 characters');
       }
       const challenge = await postChallenge();
       const { publicPem } = await ensureRSA();
       const agent = await getAgent();
       // Pre-unlock local EOA with provided password to avoid unlock dialog
       if (agent.kind === 'local') {
         await ensureEOA(password);
       }
       // --- Network / chain handling (unified with login) ---
       if (EXPECTED_CHAIN_ID && agent.getChainId) {
         try {
           const current = await agent.getChainId();
           if (current !== EXPECTED_CHAIN_ID) {
             if ((agent as any).switchChain) {
               try {
                 await (agent as any).switchChain(EXPECTED_CHAIN_ID);
               } catch (e) {
                 throw new Error(`Wrong network (${current}). Failed to auto-switch to ${EXPECTED_CHAIN_ID}: ${(e as Error).message}`);
               }
             } else {
               throw new Error(`Wrong network (${current}). Please switch to ${EXPECTED_CHAIN_ID} and retry registration.`);
             }
           }
         } catch {
           // ignore inability to read chain id before connect
         }
       }
       const address = await agent.getAddress();
       const message: LoginMessage = { address, nonce: challenge.nonce as `0x${string}` };
       const curCid = agent.getChainId ? await agent.getChainId() : undefined;
       const domain: TypedDataDomain = (agent.kind === 'metamask' && curCid)
         ? { ...LOGIN_DOMAIN, chainId: curCid }
         : LOGIN_DOMAIN;
       const TYPES: Record<string, TypedDataField[]> = toEthersTypes(LOGIN_TYPES);
       let signature: string;
       try {
         signature = await agent.signTypedData(domain, TYPES, message as unknown as Record<string, unknown>);
       } catch (e: any) {
         const code = e?.code ?? e?.error?.code;
         const msg: string = e?.message || '';
         if (code === 4001 || code === 'ACTION_REJECTED' || /user rejected/i.test(msg)) {
           throw new Error('Signature request was cancelled');
         }
         throw new Error('Failed to sign the registration challenge');
       }
       const recovered = ethers.verifyTypedData(domain, TYPES, message, signature);
       if (recovered.toLowerCase() !== address.toLowerCase()) throw new Error('Signature verification failed');
       const payload: RegisterPayload = {
          challenge_id: challenge.challenge_id,
          eth_address: address,
          rsa_public: publicPem,
          display_name: displayName || '',
          typed_data: { domain, types: TYPES, primaryType: "LoginChallenge", message },
          signature,
        };
       const tokens = await postRegister(payload);
       localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
       localStorage.setItem('REFRESH_TOKEN', tokens.refresh);
       localStorage.setItem(ADDRESS_KEY, address);
       localStorage.setItem(AUTH_METHOD_KEY, 'eoa');
       localStorage.removeItem(TON_ADDRESS_KEY);
       if (displayName) localStorage.setItem('dfsp_display_name', displayName);
       let backupData: Blob;
       if (agent.kind === 'local') {
         // EOA already ensured; create full backup with the same password
         backupData = await createBackupBlob(password);
       } else {
         backupData = new Blob([JSON.stringify({ notice: 'External wallet \u2013 create full backup after local EOA generation if needed.' }, null, 2)], { type: 'application/json' });
       }
       setUser({ address, displayName, hasBackup: false });
       return { backupData };
   };

  const restoreAccount = async (file: File, password: string) => {
    // clear stale tokens/session before restore to avoid redirect loops when coming from logged-out state
    if (!user) {
      try {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem('REFRESH_TOKEN');
        bumpSessionGen();
      } catch { /* ignore */ }
    }
    const res = await restoreFromBackup(file, password);
    // RSA-only backups do not carry an EOA, so skip auto-login and let user choose external wallet
    if (res.mode === 'RSA-only') {
      if (user) {
        setUser({ ...user, hasBackup: true });
      } else {
        setUser(null);
      }
      return res;
    }
    await login({ unlockPassword: password });
    setUser(prev => prev ? { ...prev, hasBackup: true } : null);
    return res;
   };

  const logout = () => {
     // soft logout: leave wallet session intact, just clear auth tokens
     localStorage.removeItem(ACCESS_TOKEN_KEY);
     localStorage.removeItem('REFRESH_TOKEN');
     localStorage.removeItem(AUTH_METHOD_KEY);
     localStorage.removeItem(TON_ADDRESS_KEY);
     // Do not clear address/display name so UI can prefill
     // localStorage.removeItem(ADDRESS_KEY);
     // localStorage.removeItem('dfsp_display_name');
    bumpSessionGen();
    try { window.dispatchEvent(new CustomEvent('dfsp:logout')); } catch { /* ignore */ }
     setUser(null);
     // Force Local agent after leaving auth or switching forms
     try { setSelectedAgentKind('local'); } catch { /* ignore */ }
   };

  const updateBackupStatus = (hasBackup: boolean) => {
    setUser(prev => prev ? { ...prev, hasBackup } : prev);
  };

  return (
    <AuthContext.Provider value={{
      user,
      isAuthenticated: !!user,
      isLoading,
      login,
      loginWithTon,
      register,
      logout,
      restoreAccount,
      updateBackupStatus,
    }}>
      {children}
    </AuthContext.Provider>
  );
}
