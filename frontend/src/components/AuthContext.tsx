/* eslint-disable react-refresh/only-export-components */
/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { createContext, useState, useEffect, ReactNode } from 'react';
import { hasEOA, ensureEOA, ensureRSA, createBackupBlob, restoreFromBackup, type LoginMessage, LOGIN_TYPES as KC_LOGIN_TYPES, LOGIN_DOMAIN as KC_LOGIN_DOMAIN } from '@/lib/keychain';
import { postChallenge, postLogin, postRegister, ACCESS_TOKEN_KEY, type RegisterPayload, type TypedLoginData } from '@/lib/api';
import { ethers, type TypedDataDomain, type TypedDataField } from 'ethers';
import { getAgent } from '@/lib/agent/manager';
import { ensureUnlockedOrThrow } from '@/lib/unlock';

const LOGIN_DOMAIN: TypedDataDomain = KC_LOGIN_DOMAIN;
const LOGIN_TYPES: Record<string, TypedDataField[]> = KC_LOGIN_TYPES;
const EXPECTED_CHAIN_ID = Number((import.meta as any).env?.VITE_CHAIN_ID || 0);
const ADDRESS_KEY = 'dfsp_address';
const SESSION_GEN_KEY = 'SESSION_GEN';
function bumpSessionGen() {
  try { localStorage.setItem(SESSION_GEN_KEY, crypto.randomUUID()); } catch { /* ignore */ }
}

interface User {
  address: string;
  displayName?: string;
  hasBackup: boolean;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: () => Promise<void>;
  register: (password: string, confirmPassword: string, displayName?: string) => Promise<{ backupData: Blob }>;
  logout: () => void;
  restoreAccount: (file: File, password: string) => Promise<void>;
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
        const backup = await hasEOA();
        if (address) {
          setUser({ address, displayName: storedName || undefined, hasBackup: backup });
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

  const login = async () => {
       const challenge = await postChallenge();
       const agent = await getAgent();
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
       } catch (e) {
         throw new Error(`Login signing failed: ${(e as Error).message}`);
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
       bumpSessionGen();
       const storedName = localStorage.getItem('dfsp_display_name');
       const backup = await hasEOA();
       setUser({ address, displayName: storedName || undefined, hasBackup: backup });
   };

  const register = async (
    password: string,
    confirmPassword: string,
    displayName?: string
  ): Promise<{ backupData: Blob }> => {
       if (password !== confirmPassword) throw new Error('Passwords do not match');
       const hasUpper = /[A-Z]/.test(password);
       const hasLower = /[a-z]/.test(password);
       const hasDigit = /\d/.test(password);
       if (password.length < 12 || !(hasUpper && hasLower && hasDigit)) {
         throw new Error('Password must be at least 12 characters and include upper/lower case and a digit');
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
       } catch (e) {
         throw new Error(`Registration signing failed: ${(e as Error).message}`);
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
    await restoreFromBackup(file, password);
    await login();
    setUser(prev => prev ? { ...prev, hasBackup: true } : null);
   };

  const logout = () => {
     // soft logout: leave wallet session intact, just clear auth tokens
     localStorage.removeItem(ACCESS_TOKEN_KEY);
     localStorage.removeItem('REFRESH_TOKEN');
     // Do not clear address/display name so UI can prefill
     // localStorage.removeItem(ADDRESS_KEY);
     // localStorage.removeItem('dfsp_display_name');
    bumpSessionGen();
    try { window.dispatchEvent(new CustomEvent('dfsp:logout')); } catch { /* ignore */ }
     setUser(null);
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
      register,
      logout,
      restoreAccount,
      updateBackupStatus,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

