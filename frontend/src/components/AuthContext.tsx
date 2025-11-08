/* eslint-disable @typescript-eslint/no-explicit-any */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { hasEOA, ensureEOA, ensureRSA, createBackupBlob, restoreFromBackup, type LoginMessage, LOGIN_TYPES as KC_LOGIN_TYPES, LOGIN_DOMAIN as KC_LOGIN_DOMAIN } from '@/lib/keychain';
import { postChallenge, postLogin, postRegister, ACCESS_TOKEN_KEY, type RegisterPayload, type TypedLoginData } from '@/lib/api';
import { ethers, type TypedDataDomain, type TypedDataField } from 'ethers';
import { getAgent } from '@/lib/agent/manager';
import React from 'react';

const LOGIN_DOMAIN: TypedDataDomain = KC_LOGIN_DOMAIN;
const LOGIN_TYPES: Record<string, TypedDataField[]> = KC_LOGIN_TYPES;
const EXPECTED_CHAIN_ID = Number((import.meta as any).env?.VITE_CHAIN_ID || 0);
const ADDRESS_KEY = 'dfsp_address';

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

const AuthContext = createContext<AuthContextType | undefined>(undefined);

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
       // Enforce chain only for metamask with expected chain id; skip for walletconnect to allow signing even if network mismatch
       if (EXPECTED_CHAIN_ID && agent.kind === 'metamask' && agent.getChainId) {
         const current = await agent.getChainId();
         if (current !== EXPECTED_CHAIN_ID) {
           throw new Error(`MetaMask: wrong network (${current}). Switch to ${EXPECTED_CHAIN_ID} and retry.`);
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
       if (password.length < 12) throw new Error('Password must be at least 12 characters');
       const challenge = await postChallenge();
       const { publicPem } = await ensureRSA();
       const agent = await getAgent();
       if (EXPECTED_CHAIN_ID && agent.kind === 'metamask' && agent.getChainId) {
         const current = await agent.getChainId();
         if (current !== EXPECTED_CHAIN_ID) {
           throw new Error(`MetaMask: wrong network (${current}). Switch and retry registration.`);
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
         await ensureEOA();
         backupData = await createBackupBlob(password);
       } else {
         backupData = new Blob([JSON.stringify({ notice: 'External wallet – create full backup after local EOA generation if needed.' }, null, 2)], { type: 'application/json' });
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
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem('REFRESH_TOKEN');
    localStorage.removeItem(ADDRESS_KEY);
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

export function useAuth(): AuthContextType {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
