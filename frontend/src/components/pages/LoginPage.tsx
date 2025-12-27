import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../useAuth';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { Key, AlertCircle } from 'lucide-react';
import { hasEOA, isEOAUnlocked } from '@/lib/keychain';
import { getAgent } from '@/lib/agent/manager';
import { getErrorMessage } from '@/lib/errors';
import AgentSelector from '../AgentSelector';
import TonConnectLogo from '@/assets/icons/TonConnect-Logo.svg';
import type * as React from "react";

type LoginState = 'idle' | 'checking' | 'unlocking' | 'signing' | 'error' | 'success';
type TonState = 'idle' | 'connecting' | 'signing' | 'error' | 'success';

export default function LoginPage() {
  const [state, setState] = useState<LoginState>('idle');
  const [tonState, setTonState] = useState<TonState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [tonError, setTonError] = useState('');
  const { login, loginWithTon } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [keysExist, setKeysExist] = useState<boolean | null>(null);

  // Check if keys exist on mount (optional)
  useEffect(() => {
    hasEOA().then(setKeysExist);
    // Не форсим Local signer при заходе на Login: пользователь может выбрать MetaMask/WalletConnect.
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setState('checking');
      setErrorMessage('');
      // Prepare UI state based on agent
      const agent = await getAgent();
      if (agent.kind === 'local' && !isEOAUnlocked()) {
        setState('unlocking');
      } else {
        setState('signing');
      }
      await login();
      setState('success');
      const params = new URLSearchParams(location.search);
      const redirect = params.get('redirect');
      const safeRedirect = redirect && redirect.startsWith('/') ? redirect : '/files';
      navigate(safeRedirect);
    } catch (error) {
      setState('error');
      setErrorMessage(getErrorMessage(error, 'Authentication failed'));
    }
  };

  const handleTonLogin = async () => {
    try {
      setTonState('connecting');
      setTonError('');
      await loginWithTon();
      setTonState('success');
      const params = new URLSearchParams(location.search);
      const redirect = params.get('redirect');
      const safeRedirect = redirect && redirect.startsWith('/') ? redirect : '/files';
      navigate(safeRedirect);
    } catch (error) {
      setTonState('error');
      setTonError(getErrorMessage(error, 'TON login failed'));
    }
  };

  const getStateMessage = () => {
    switch (state) {
      case 'checking':
        return 'Loading keys...';
      case 'unlocking':
        return 'Waiting for unlock...';
      case 'signing':
        return 'Signing challenge...';
      case 'success':
        return 'Success!';
      default:
        return '';
    }
  };

  const isLoading = state === 'checking' || state === 'unlocking' || state === 'signing';
  const isTonLoading = tonState === 'connecting' || tonState === 'signing';

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
            <Key className="h-8 w-8 text-primary" />
          </div>
          <h1 className="mb-2">Login</h1>
          <div className="flex flex-col items-center gap-3 mt-2">
            <AgentSelector showInlineError={false} />
            <Button
              type="button"
              variant="outline"
              className="w-full max-w-xs gap-2"
              onClick={handleTonLogin}
              disabled={isTonLoading}
            >
              <img src={TonConnectLogo} alt="TON Connect" className="h-5 w-5" />
              {isTonLoading ? 'Awaiting TON signature...' : 'Login with TON Connect'}
            </Button>
            {tonError && (
              <Alert variant="destructive" className="w-full max-w-xs">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{tonError}</AlertDescription>
              </Alert>
            )}
          </div>
          <p className="text-muted-foreground">
            {keysExist === false
              ? 'No local keys found — you can still login with MetaMask/WalletConnect'
              : 'Sign in with your selected signer'}
          </p>
        </div>

        <div className="bg-card p-8 rounded-lg shadow-sm border border-border">
          <form onSubmit={handleSubmit} className="space-y-6">
            {keysExist === false && (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  No local keys found. You can login with MetaMask/WalletConnect, or restore from backup.
                </AlertDescription>
              </Alert>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isLoading}
            >
              {isLoading ? getStateMessage() : 'Login'}
            </Button>

            {state === 'error' && errorMessage && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            )}

            {isLoading && (
              <div className="text-center text-sm text-gray-600">
                {getStateMessage()}
              </div>
            )}
          </form>

          <div className="mt-6 pt-6 border-t border-gray-200">
            <Link
              to="/restore"
              className="text-sm text-blue-600 hover:text-blue-700 flex items-center justify-center gap-2"
            >
              <Key className="h-4 w-4" />
              Restore from backup (.dfspkey)
            </Link>
          </div>
        </div>

        <div className="mt-6 text-center">
          <span className="text-gray-600 text-sm">Don't have an account? </span>
          <Link to="/register" className="text-blue-600 hover:text-blue-700 text-sm">
            Create Account
          </Link>
        </div>
      </div>
    </div>
  );
}
