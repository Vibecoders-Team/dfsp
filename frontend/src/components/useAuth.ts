/* Hook re-exported from AuthContext to satisfy react-refresh rule */
import { useContext } from 'react';
import { AuthContext } from './AuthContext';
import type { AuthContextType } from './AuthContext';

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

