import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../useAuth';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { Key, AlertCircle } from 'lucide-react';
import { hasEOA, isEOAUnlocked } from '@/lib/keychain';
import { getAgent } from '@/lib/agent/manager';
import { getErrorMessage } from '@/lib/errors';
import AgentSelector from '../AgentSelector';

type LoginState = 'idle' | 'checking' | 'unlocking' | 'signing' | 'error' | 'success';

export default function LoginPage() {
  const [state, setState] = useState<LoginState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const [keysExist, setKeysExist] = useState<boolean | null>(null);

  // Check if keys exist on mount (optional)
  useEffect(() => {
    hasEOA().then(setKeysExist);
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
      navigate('/files');
    } catch (error) {
      setState('error');
      setErrorMessage(getErrorMessage(error, 'Authentication failed'));
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

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4">
            <Key className="h-8 w-8 text-blue-600" />
          </div>
          <h1 className="mb-2">Login</h1>
          <div className="flex justify-center mt-2"><AgentSelector /></div>
          <p className="text-gray-600">
            {keysExist === false 
              ? 'No local keys found — you can still login with MetaMask/WalletConnect'
              : 'Sign in with your selected signer'}
          </p>
        </div>

        <div className="bg-white p-8 rounded-lg shadow-sm border border-gray-200">
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
              to="/settings/keys"
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
