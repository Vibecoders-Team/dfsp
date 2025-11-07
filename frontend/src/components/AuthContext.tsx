/* eslint-disable @typescript-eslint/no-explicit-any */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { hasEOA, ensureEOA, ensureRSA, createBackupBlob, restoreFromBackup, type LoginMessage, LOGIN_TYPES as KC_LOGIN_TYPES, LOGIN_DOMAIN as KC_LOGIN_DOMAIN } from '@/lib/keychain';
import { postChallenge, postLogin, postRegister, ACCESS_TOKEN_KEY, type RegisterPayload, type TypedLoginData } from '@/lib/api';
import { ethers, type TypedDataDomain, type TypedDataField } from 'ethers';
import { getAgent } from '@/lib/agent/manager';

const LOGIN_DOMAIN: TypedDataDomain = KC_LOGIN_DOMAIN;
const LOGIN_TYPES: Record<string, TypedDataField[]> = KC_LOGIN_TYPES;
const EXPECTED_CHAIN_ID = Number((import.meta as any).env?.VITE_CHAIN_ID || 0);

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

        if (token && await hasEOA()) {
          const eoa = await ensureEOA();
          const address = eoa.address;

          // Try to get display name from localStorage
          const storedName = localStorage.getItem('dfsp_display_name');

          setUser({
            address,
            displayName: storedName || undefined,
            hasBackup: true // assume true if keys exist
          });
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        // Clear invalid session
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem('REFRESH_TOKEN');
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = async () => {
       const challenge = await postChallenge();
       const agent = await getAgent();
       if (EXPECTED_CHAIN_ID && agent.kind === 'metamask' && agent.getChainId) {
         const current = await agent.getChainId();
         if (current !== EXPECTED_CHAIN_ID) {
           throw new Error(`MetaMask: неверная сеть (${current}). Нажмите 'Switch' в панели Signer и повторите попытку.`);
         }
       }
       const address = await agent.getAddress();
       const message: LoginMessage = { address, nonce: challenge.nonce as `0x${string}` };
       const curCid = agent.getChainId ? await agent.getChainId() : undefined;
       const domain: TypedDataDomain = (agent.kind === 'metamask' && curCid)
         ? { ...LOGIN_DOMAIN, chainId: curCid }
         : LOGIN_DOMAIN;
       const TYPES: Record<string, TypedDataField[]> = toEthersTypes(LOGIN_TYPES);
       const signature = await agent.signTypedData(domain, TYPES, message as unknown as Record<string, unknown>);
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
        const storedName = localStorage.getItem('dfsp_display_name');
        setUser({ address, displayName: storedName || undefined, hasBackup: true });
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
           throw new Error(`MetaMask: неверная сеть (${current}). Нажмите 'Switch' и повторите регистрацию.`);
         }
       }
       const address = await agent.getAddress();
       const message: LoginMessage = { address, nonce: challenge.nonce as `0x${string}` };
       const curCid = agent.getChainId ? await agent.getChainId() : undefined;
       const domain: TypedDataDomain = (agent.kind === 'metamask' && curCid)
         ? { ...LOGIN_DOMAIN, chainId: curCid }
         : LOGIN_DOMAIN;
       const TYPES: Record<string, TypedDataField[]> = toEthersTypes(LOGIN_TYPES);
       const signature = await agent.signTypedData(domain, TYPES, message as unknown as Record<string, unknown>);
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
        if (displayName) localStorage.setItem('dfsp_display_name', displayName);
        // Ensure local EOA exists so backup includes it (until RSA-only backup is implemented)
        await ensureEOA();
        const backupData = await createBackupBlob(password);
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
    setUser(null);
  };

  const updateBackupStatus = (hasBackup: boolean) => {
    if (user) {
      setUser({ ...user, hasBackup });
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        restoreAccount,
        updateBackupStatus
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

/* eslint-disable react-refresh/only-export-components */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
