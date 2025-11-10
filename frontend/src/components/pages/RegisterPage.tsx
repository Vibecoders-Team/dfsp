import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../useAuth';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Checkbox } from '../ui/checkbox';
import { Alert, AlertDescription } from '../ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Eye, EyeOff, Key, AlertCircle, CheckCircle2, Download } from 'lucide-react';
import { Progress } from '../ui/progress';
import AgentSelector from '../AgentSelector';
import { getErrorMessage } from '@/lib/errors';

type RegisterState = 'idle' | 'generating' | 'backup_required' | 'registering' | 'success' | 'error';

export default function RegisterPage() {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [state, setState] = useState<RegisterState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [backupData, setBackupData] = useState<Blob | null>(null);
  const [backupDownloaded, setBackupDownloaded] = useState(false);
  const [showBackupModal, setShowBackupModal] = useState(false);
  const { register: registerUser, login, updateBackupStatus } = useAuth();
  const navigate = useNavigate();

  const getPasswordStrength = (): 'weak' | 'medium' | 'strong' => {
    if (password.length < 12) return 'weak';
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasDigit = /\d/.test(password);
    const hasSpecial = /[^A-Za-z0-9]/.test(password);
    const score = [hasUpper, hasLower, hasDigit, hasSpecial].filter(Boolean).length;
    if (score >= 3 && password.length >= 16) return 'strong';
    if (score >= 2 && password.length >= 12) return 'medium';
    return 'weak';
  };
  const passwordStrength = password ? getPasswordStrength() : null;
  const passwordsMatch = password && confirmPassword && password === confirmPassword;

  const isFormValid = () => (
    acceptTerms &&
    password.length >= 12 &&
    /[A-Z]/.test(password) && /[a-z]/.test(password) && /\d/.test(password) &&
    passwordsMatch
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid()) {
      setErrorMessage('Please provide a password (min 12 chars, upper/lowercase, digit) and accept Terms');
      setState('error');
      return;
    }
    try {
      setState('generating');
      setErrorMessage('');
      const result = await registerUser(password, confirmPassword, displayName || undefined);
      setBackupData(result.backupData);
      setState('backup_required');
      setShowBackupModal(true);
    } catch (error) {
      setState('error');
      setErrorMessage(getErrorMessage(error, 'Registration failed'));
    }
  };

  const handleDownloadBackup = () => {
    if (!backupData) return;

    const url = URL.createObjectURL(backupData);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dfsp-backup-${Date.now()}.dfspkey`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setBackupDownloaded(true);
  };

  const handleSkipBackup = async () => {
    setShowBackupModal(false);
    await completeRegistration(false);
  };

  const handleContinueWithBackup = async () => {
    setShowBackupModal(false);
    await completeRegistration(true);
  };

  const completeRegistration = async (hasBackup: boolean) => {
    try {
      setState('registering');
      // After registration, keys are already in IndexedDB, just login
      await login();
      updateBackupStatus(hasBackup);
      
      setState('success');
      navigate('/files');
    } catch (error) {
      setState('error');
      setErrorMessage(getErrorMessage(error, 'Registration failed'));
    }
  };

  const getStateMessage = () => {
    switch (state) {
      case 'generating':
        return 'Generating keys...';
      case 'registering':
        return 'Registering...';
      case 'success':
        return 'Success!';
      default:
        return '';
    }
  };

  const isLoading = state === 'generating' || state === 'registering';

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4">
            <Key className="h-8 w-8 text-blue-600" />
          </div>
          <h1 className="mb-2">Create Account</h1>
          <p className="text-gray-600">
            Set up your secure decentralized file sharing account. You can sign with Local keys, MetaMask, or WalletConnect.
          </p>
          <div className="flex justify-center mt-2"><AgentSelector /></div>
        </div>

        <div className="bg-white p-8 rounded-lg shadow-sm border border-gray-200">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="displayName">Display Name (Optional)</Label>
              <Input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={isLoading}
                placeholder="Enter your display name"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password (for local key encryption)</Label>
              <div className="relative">
                <Input id="password" type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} disabled={isLoading} placeholder="Minimum 12 characters" className="pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600" disabled={isLoading}>
                  {showPassword ? (<EyeOff className="h-4 w-4" />) : (<Eye className="h-4 w-4" />)}
                </button>
              </div>
              {password && passwordStrength && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Progress value={passwordStrength === 'weak' ? 33 : passwordStrength === 'medium' ? 66 : 100} className="h-1.5" />
                    <span className={`text-xs ${passwordStrength === 'weak' ? 'text-red-600' : passwordStrength === 'medium' ? 'text-yellow-600' : 'text-green-600'}`}>
                      {passwordStrength.charAt(0).toUpperCase() + passwordStrength.slice(1)}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">Use mixed case, digits, and special characters</p>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <div className="relative">
                <Input id="confirmPassword" type={showConfirmPassword ? 'text' : 'password'} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} disabled={isLoading} placeholder="Re-enter your password" className="pr-10" />
                <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600" disabled={isLoading}>
                  {showConfirmPassword ? (<EyeOff className="h-4 w-4" />) : (<Eye className="h-4 w-4" />)}
                </button>
              </div>
              {confirmPassword && (
                <div className="flex items-center gap-2">
                  {passwordsMatch ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                      <span className="text-xs text-green-600">Passwords match</span>
                    </>
                  ) : (
                    <>
                      <AlertCircle className="h-4 w-4 text-red-600" />
                      <span className="text-xs text-red-600">Passwords do not match</span>
                    </>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-start gap-3">
              <Checkbox
                id="terms"
                checked={acceptTerms}
                onCheckedChange={(checked) => setAcceptTerms(checked === true)}
                disabled={isLoading}
              />
              <Label htmlFor="terms" className="cursor-pointer leading-relaxed">
                I accept the Terms of Service and Privacy Policy
              </Label>
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={!isFormValid() || isLoading}
            >
              {isLoading ? getStateMessage() : 'Create Account'}
            </Button>

            {state === 'error' && errorMessage && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            )}
          </form>
        </div>

        <div className="mt-6 text-center">
          <span className="text-gray-600 text-sm">Already have an account? </span>
          <Link to="/login" className="text-blue-600 hover:text-blue-700 text-sm">
            Login
          </Link>
        </div>
      </div>

      <Dialog open={showBackupModal} onOpenChange={() => {}}>
        <DialogContent className="sm:max-w-md" onPointerDownOutside={(e) => e.preventDefault()}>
          <DialogHeader>
            <DialogTitle>Backup Your Keys</DialogTitle>
            <DialogDescription>
              Your encryption keys are critical for accessing your files. Download the backup file now to ensure you never lose access.
            </DialogDescription>
          </DialogHeader>
          
          <div className="py-4">
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Without this backup, you cannot recover your account if you forget your password. Store it securely.
              </AlertDescription>
            </Alert>
          </div>

          <DialogFooter className="flex-col sm:flex-col gap-2">
            <Button
              onClick={handleDownloadBackup}
              className="w-full gap-2"
            >
              <Download className="h-4 w-4" />
              Download .dfspkey
            </Button>
            
            <Button
              onClick={handleContinueWithBackup}
              variant="default"
              className="w-full"
              disabled={!backupDownloaded}
            >
              Continue
            </Button>
            
            <Button
              onClick={handleSkipBackup}
              variant="ghost"
              className="w-full"
            >
              I'll do it later
            </Button>
            
            {!backupDownloaded && (
              <p className="text-xs text-center text-gray-500 mt-2">
                Download the backup to enable the Continue button
              </p>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
