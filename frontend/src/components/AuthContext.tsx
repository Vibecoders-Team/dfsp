/* eslint-disable react-refresh/only-export-components */
/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { createContext, useState, useEffect, ReactNode } from 'react';
import { hasEOA, ensureEOA, ensureRSA, createBackupBlob, restoreFromBackup, type LoginMessage, LOGIN_TYPES as KC_LOGIN_TYPES, LOGIN_DOMAIN as KC_LOGIN_DOMAIN, unlockEOA, type RestoreResult } from '@/lib/keychain';
import { postChallenge, postLogin, postRegister, postTonChallenge, postTonLogin, updateRsaPublic, ACCESS_TOKEN_KEY, type RegisterPayload, type TypedLoginData, type TonSignPayload } from '@/lib/api';
import type { TypedDataDomain, TypedDataField } from 'ethers';
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
  register: (password?: string, confirmPassword?: string, displayName?: string) => Promise<{ backupData: Blob }>;
  logout: () => void;
  restoreAccount: (file: File, password: string) => Promise<RestoreResult>;
  updateBackupStatus: (hasBackup: boolean) => void;
  updateDisplayName: (displayName: string) => void;
}

export type { AuthContextType };
export const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Helper to convert types for ethers v6
function toEthersTypes(src: Record<string, readonly TypedDataField[]>): Record<string, TypedDataField[]> {
  return Object.fromEntries(
    Object.entries(src)
      .filter(([k]) => k !== "EIP712Domain")
      .map(([k, arr]) => [k, Array.from(arr)])
  ) as Record<string, TypedDataField[]>;
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
          // Sync agent kind with auth method on session restore
          if (authMethod === 'ton') {
            setSelectedAgentKind('ton');
          }
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
       // DEBUG: Check time skew between client and server
       try {
         const timeRes = await fetch((import.meta as any).env?.VITE_API_BASE + '/time');
         if (timeRes.ok) {
           const timeData = await timeRes.json();
           const serverTime = timeData.server_time_unix;
           const clientTime = Math.floor(Date.now() / 1000);
           const skew = clientTime - serverTime;
           console.info('[Auth] Time skew check: server=%d client=%d skew=%d seconds', serverTime, clientTime, skew);
           if (Math.abs(skew) > 300) {
             console.warn('[Auth] WARNING: Time skew > 5 minutes! This may cause JWT issues.');
           }
         }
       } catch (e) {
         console.warn('[Auth] Could not check server time:', e);
       }

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
       const { ethers } = await import('ethers');
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

       // DEBUG: Log token receipt and storage
       console.info('[Auth] Received tokens, access length:', tokens.access?.length, 'refresh length:', tokens.refresh?.length);
       if (tokens.access) {
         // Decode JWT payload (middle part) to check iat/exp
         try {
           const parts = tokens.access.split('.');
           if (parts.length === 3) {
             const payload = JSON.parse(atob(parts[1]));
             const now = Math.floor(Date.now() / 1000);
             console.info('[Auth] JWT iat:', payload.iat, 'exp:', payload.exp, 'client_now:', now, 'iat_diff:', now - payload.iat, 'ttl:', payload.exp - now);
           }
         } catch { /* ignore parse errors */ }
       }

       localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
       localStorage.setItem('REFRESH_TOKEN', tokens.refresh);

       // Verify token was saved
       const savedToken = localStorage.getItem(ACCESS_TOKEN_KEY);
       console.info('[Auth] Token saved, verified length:', savedToken?.length, 'matches:', savedToken === tokens.access);

       localStorage.setItem(ADDRESS_KEY, address);
       localStorage.setItem(AUTH_METHOD_KEY, 'eoa');
       localStorage.removeItem(TON_ADDRESS_KEY);
       bumpSessionGen();
       const storedName = localStorage.getItem('dfsp_display_name');
       const backup = await hasEOA();
       setUser({ address, displayName: storedName || undefined, hasBackup: backup, authMethod: 'eoa' });
   };

  const loginWithTon = async () => {
    try {
      const ton = await getTonConnect();

      // Try to connect wallet if not connected
      if (!ton.wallet) {
        try {
          await ton.connectWallet();
        } catch (error: any) {
          // Handle wallet connection cancellation
          if (error?.message?.includes?.('Wallet was not connected') ||
              error?.message?.includes?.('TON_CONNECT_SDK_ERROR') ||
              error?.code === 'USER_CANCELLED' ||
              error?.code === 'CANCELLED_BY_USER') {
            throw new Error('Wallet connection was cancelled');
          }
          throw new Error(`Failed to connect wallet: ${error?.message || 'Unknown error'}`);
        }
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
      try { setSelectedAgentKind('ton'); } catch { /* ignore */ }

      // Handle signing with proper error catching
      let signed: any;
      try {
        signed = await ton.signData({ type: "binary", bytes: challenge.nonce });
      } catch (error: any) {
        // Handle signing cancellation
        if (error?.message?.includes?.('User declined') ||
            error?.message?.includes?.('Cancelled') ||
            error?.message?.includes?.('rejected') ||
            error?.code === 'USER_CANCELLED' ||
            error?.code === 'CANCELLED_BY_USER') {
          throw new Error('Signing was cancelled');
        }
        throw new Error(`Failed to sign challenge: ${error?.message || 'Unknown error'}`);
      }

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

      const derivedEth = await deriveEthFromTonPub(pubkeyHex);
      localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
      localStorage.setItem('REFRESH_TOKEN', tokens.refresh);
      localStorage.setItem(ADDRESS_KEY, derivedEth);
      localStorage.setItem(TON_ADDRESS_KEY, tonAddress);
      localStorage.setItem(AUTH_METHOD_KEY, 'ton');

      // Generate RSA keypair for TON users and publish to server
      // This is needed so other users can share files with this TON user
      try {
        const { publicPem } = await ensureRSA();
        await updateRsaPublic(publicPem);
        console.info('[Auth] RSA public key published for TON user');
      } catch (rsaError) {
        console.warn('[Auth] Failed to publish RSA public key:', rsaError);
        // Don't fail the login, but the user won't be able to receive shared files
      }

      bumpSessionGen();
      setUser({ address: derivedEth, displayName: 'TON user', hasBackup: false, authMethod: 'ton', tonAddress });
    } catch (error: any) {
      // Clean up any partial state if needed
      console.warn('[Auth] TON login failed:', error);

      // Re-throw with normalized error message
      if (error?.message?.includes?.('cancelled') ||
          error?.message?.includes?.('Cancelled') ||
          error?.message?.includes?.('declined')) {
        throw new Error('TON login was cancelled');
      }

      throw error;
    }
  };

  const register = async (
    password?: string,
    confirmPassword?: string,
    displayName?: string
  ): Promise<{ backupData: Blob }> => {
       const agent = await getAgent();

       // Password is only required for local signer (we encrypt the local EOA in browser storage)
       if (agent.kind === 'local') {
         const pwd = password ?? '';
         const cpwd = confirmPassword ?? '';
         if (pwd !== cpwd) throw new Error('Passwords do not match');
         if (pwd.length < 8) {
           throw new Error('Password must be at least 8 characters');
         }
         // Pre-unlock/generate local EOA with provided password to avoid unlock dialog
         await ensureEOA(pwd);
       }

       const challenge = await postChallenge();
       const { publicPem } = await ensureRSA();

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
       const { ethers: _ethers } = await import('ethers');
       const recovered2 = _ethers.verifyTypedData(domain, TYPES, message, signature);
       if (recovered2.toLowerCase() !== address.toLowerCase()) throw new Error('Signature verification failed');
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
         // For local EOA, create a backup blob containing the RSA private key
         const blob = await createBackupBlob(password ?? '');
         backupData = blob as Blob;
       } else {
         // For remote agents, no backup is created
         backupData = new Blob();
       }
       bumpSessionGen();
       setUser({ address, displayName: displayName || undefined, hasBackup: true, authMethod: 'eoa' });
       return { backupData };
   };

  const logout = () => {
     setUser(null);
     localStorage.removeItem(ACCESS_TOKEN_KEY);
     localStorage.removeItem('REFRESH_TOKEN');
     localStorage.removeItem(ADDRESS_KEY);
     localStorage.removeItem(AUTH_METHOD_KEY);
     localStorage.removeItem(TON_ADDRESS_KEY);
     // Reset agent kind to local on logout to avoid stale TON agent on next login
     setSelectedAgentKind('local');
     bumpSessionGen();
  };

  const restoreAccount = async (file: File, password: string) => {
     return restoreFromBackup(file, password);
  };

  const updateBackupStatus = (hasBackup: boolean) => {
     setUser(u => u ? { ...u, hasBackup } : u);
     try {
       if (hasBackup) {
         const address = localStorage.getItem(ADDRESS_KEY);
         const displayName = localStorage.getItem('dfsp_display_name');
         const authMethod = (localStorage.getItem(AUTH_METHOD_KEY) as 'eoa' | 'ton' | null) || 'eoa';
         const tonAddress = localStorage.getItem(TON_ADDRESS_KEY) || undefined;
         if (address) {
           setUser({ address, displayName: displayName || undefined, hasBackup, authMethod, tonAddress });
         }
       }
     } catch { /* ignore */ }
  };

  const updateDisplayName = (displayName: string) => {
     setUser(u => u ? { ...u, displayName } : u);
     localStorage.setItem('dfsp_display_name', displayName);
  };

  const isAuthenticated = !!user && !isLoading;
  const value = { user, isAuthenticated, isLoading, login, loginWithTon, register, logout, restoreAccount, updateBackupStatus, updateDisplayName };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
