import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { Key, AlertCircle } from 'lucide-react';
import { hasEOA } from '../../lib/keychain';
import { getErrorMessage } from '../../lib/errors';

type LoginState = 'idle' | 'checking' | 'signing' | 'error' | 'success';

export default function LoginPage() {
  const [state, setState] = useState<LoginState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();
  const [keysExist, setKeysExist] = useState<boolean | null>(null);

  // Check if keys exist on mount
  useEffect(() => {
    hasEOA().then(setKeysExist);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      setState('checking');
      setErrorMessage('');
      
      // Check if keys exist
      const exists = await hasEOA();
      if (!exists) {
        setErrorMessage('No keys found. Please register first or restore from backup.');
        setState('error');
        return;
      }

      setState('signing');
      
      // Login with existing keys from IndexedDB
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
      case 'signing':
        return 'Signing challenge...';
      case 'success':
        return 'Success!';
      default:
        return '';
    }
  };

  const isLoading = state === 'checking' || state === 'signing';

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4">
            <Key className="h-8 w-8 text-blue-600" />
          </div>
          <h1 className="mb-2">Login</h1>
          <p className="text-gray-600">
            {keysExist === false 
              ? 'No account found on this device' 
              : 'Sign in with your local keys'}
          </p>
        </div>

        <div className="bg-white p-8 rounded-lg shadow-sm border border-gray-200">
          <form onSubmit={handleSubmit} className="space-y-6">
            {keysExist === false && (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  No keys found. Please register or restore from backup.
                </AlertDescription>
              </Alert>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isLoading || keysExist === false}
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
