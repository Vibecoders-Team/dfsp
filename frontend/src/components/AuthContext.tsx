import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import {
  hasEOA,
  ensureEOA,
  ensureRSA,
  signLoginTyped,
  createBackupBlob,
  restoreFromBackup,
  type LoginMessage
} from '../lib/keychain';
import {
  postChallenge,
  postLogin,
  postRegister,
  ACCESS_TOKEN_KEY,
  type RegisterPayload
} from '../lib/api';
import { ethers } from 'ethers';
import { LOGIN_DOMAIN, LOGIN_TYPES } from '../lib/keychain';

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
function toEthersTypes(src: Record<string, readonly any[]>): Record<string, any[]> {
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
    try {
      // 1. Get challenge from backend
      const challenge = await postChallenge();

      // 2. Ensure we have EOA keys
      const eoa = await ensureEOA();
      const address = eoa.address as `0x${string}`;

      // 3. Prepare login message
      const message: LoginMessage = {
        address,
        nonce: challenge.nonce as `0x${string}`
      };

      // 4. Sign with local keys
      const signature = await signLoginTyped(message);

      // 5. Verify signature locally
      const TYPES = toEthersTypes(LOGIN_TYPES);
      const recovered = ethers.verifyTypedData(LOGIN_DOMAIN, TYPES, message, signature);

      if (recovered.toLowerCase() !== address.toLowerCase()) {
        throw new Error(`Signature verification failed: recovered ${recovered} ≠ ${address}`);
      }

      // 6. Send to backend
      const payload = {
        challenge_id: challenge.challenge_id,
        eth_address: address,
        typed_data: {
          domain: LOGIN_DOMAIN,
          types: TYPES,
          primaryType: "LoginChallenge" as const,
          message,
        },
        signature,
      };

      const tokens = await postLogin(payload);

      // 7. Save tokens and user data
      localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
      localStorage.setItem('REFRESH_TOKEN', tokens.refresh);

      const storedName = localStorage.getItem('dfsp_display_name');

      setUser({
        address,
        displayName: storedName || undefined,
        hasBackup: true,
      });
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  const register = async (
    password: string,
    confirmPassword: string,
    displayName?: string
  ): Promise<{ backupData: Blob }> => {
    try {
      if (password !== confirmPassword) {
        throw new Error('Passwords do not match');
      }

      if (password.length < 12) {
        throw new Error('Password must be at least 12 characters');
      }

      // 1. Get challenge
      const challenge = await postChallenge();

      // 2. Generate keys (EOA + RSA)
      const eoa = await ensureEOA();
      const { publicPem } = await ensureRSA();
      const address = eoa.address as `0x${string}`;

      // 3. Prepare and sign login message
      const message: LoginMessage = {
        address,
        nonce: challenge.nonce as `0x${string}`
      };

      const signature = await signLoginTyped(message);

      // 4. Verify locally
      const TYPES = toEthersTypes(LOGIN_TYPES);
      const recovered = ethers.verifyTypedData(LOGIN_DOMAIN, TYPES, message, signature);

      if (recovered.toLowerCase() !== address.toLowerCase()) {
        throw new Error('Signature verification failed');
      }

      // 5. Register on backend
      const payload: RegisterPayload = {
        challenge_id: challenge.challenge_id,
        eth_address: address,
        rsa_public: publicPem,
        display_name: displayName || '',
        typed_data: {
          domain: LOGIN_DOMAIN,
          types: TYPES,
          primaryType: "LoginChallenge",
          message,
        },
        signature,
      };

      const tokens = await postRegister(payload);

      // 6. Save tokens
      localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
      localStorage.setItem('REFRESH_TOKEN', tokens.refresh);
      if (displayName) {
        localStorage.setItem('dfsp_display_name', displayName);
      }

      // 7. Create backup
      const backupData = await createBackupBlob(password);

      // 8. Set user
      setUser({
        address,
        displayName,
        hasBackup: false, // will be true after they download backup
      });

      return { backupData };
    } catch (error) {
      console.error('Registration failed:', error);
      throw error;
    }
  };

  const restoreAccount = async (file: File, password: string) => {
    try {
      const { address } = await restoreFromBackup(file, password);

      // After restore, need to login
      await login();

      setUser(prev => prev ? { ...prev, hasBackup: true } : null);
    } catch (error) {
      console.error('Account restore failed:', error);
      throw error;
    }
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

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
