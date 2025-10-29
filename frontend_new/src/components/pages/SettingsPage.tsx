import { useState, useRef, useEffect } from 'react';
import type { ChangeEvent } from 'react';
import { Link, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Progress } from '../ui/progress';
import { Key, User, Shield, Download, Upload, AlertCircle, CheckCircle2, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { ensureRSA, createBackupBlob } from '../../lib/keychain';
import { publishMyKeyCard } from '../../lib/publishMyKey';

function SettingsNav() {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.endsWith('/' + path);
  };

  return (
    <nav className="space-y-1">
      <Link to="profile">
        <Button
          variant={isActive('profile') ? 'secondary' : 'ghost'}
          className="w-full justify-start gap-2"
        >
          <User className="h-4 w-4" />
          Profile
        </Button>
      </Link>
      <Link to="keys">
        <Button
          variant={isActive('keys') ? 'secondary' : 'ghost'}
          className="w-full justify-start gap-2"
        >
          <Key className="h-4 w-4" />
          Keys & Backup
        </Button>
      </Link>
      <Link to="security">
        <Button
          variant={isActive('security') ? 'secondary' : 'ghost'}
          className="w-full justify-start gap-2"
        >
          <Shield className="h-4 w-4" />
          Security
        </Button>
      </Link>
    </nav>
  );
}

export function ProfileSettings() {
  const { user } = useAuth();
  const [displayName, setDisplayName] = useState(user?.displayName || '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    setError('');
    setSuccess(false);

    try {
      // TODO: implement profile update API
      await new Promise(resolve => setTimeout(resolve, 1000));
      toast.success('Profile updated successfully');
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update profile');
    } finally {
      setIsSaving(false);
    }
  };

  const formatDate = (date: Date) => {
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2>Profile Settings</h2>
        <p className="text-gray-600">Manage your profile information</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Personal Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="displayName">Display Name</Label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={isSaving}
              placeholder="Enter your display name"
            />
          </div>

          <div className="space-y-2">
            <Label>Ethereum Address</Label>
            <div className="flex gap-2">
              <Input
                value={user?.address || ''}
                disabled
                className="flex-1"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(user?.address || '');
                  toast.success('Address copied to clipboard');
                }}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Registration Date</Label>
            <Input
              value={formatDate(new Date())}
              disabled
            />
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert>
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-800">
                Profile updated successfully
              </AlertDescription>
            </Alert>
          )}

          <div className="flex justify-end">
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function KeysSettings() {
  const { user, restoreAccount, updateBackupStatus } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restorePassword, setRestorePassword] = useState('');
  const [error, setError] = useState('');
  const [showPasswordPrompt, setShowPasswordPrompt] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [publicPem, setPublicPem] = useState<string>('');
  const [isLoadingKeys, setIsLoadingKeys] = useState(true);
  const [backupPassword, setBackupPassword] = useState('');
  const [backupBusy, setBackupBusy] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishCid, setPublishCid] = useState<string>('');
  const [publishUrl, setPublishUrl] = useState<string>('');

  useEffect(() => {
    (async () => {
      try {
        setIsLoadingKeys(true);
        const { publicPem } = await ensureRSA();
        setPublicPem(publicPem);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load keys');
      } finally {
        setIsLoadingKeys(false);
      }
    })();
  }, []);

  const handlePublishKeyCard = async () => {
    try {
      setPublishBusy(true);
      setError('');
      const { cid, url } = await publishMyKeyCard();
      setPublishCid(cid);
      setPublishUrl(url || '');
      toast.success('Public key card published', { description: cid });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to publish key card');
    } finally {
      setPublishBusy(false);
    }
  };

  const handleDownloadBackup = async () => {
    try {
      if (!backupPassword || backupPassword.length < 12) {
        setError('Set a strong password (>= 12 chars) to encrypt your backup');
        return;
      }
      setBackupBusy(true);
      const blob = await createBackupBlob(backupPassword);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dfsp-backup-${Date.now()}.dfspkey`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      updateBackupStatus(true);
      toast.success('Backup file downloaded');
      setBackupPassword('');
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create backup');
    } finally {
      setBackupBusy(false);
    }
  };

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setSelectedFile(files[0]);
      setShowPasswordPrompt(true);
      setError('');
    }
  };

  const handleRestore = async () => {
    if (!selectedFile || !restorePassword) {
      setError('Please provide password');
      return;
    }

    setIsRestoring(true);
    setError('');

    try {
      await restoreAccount(selectedFile, restorePassword);
      toast.success('Keys restored successfully');
      setShowPasswordPrompt(false);
      setRestorePassword('');
      setSelectedFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restore keys');
    } finally {
      setIsRestoring(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2>Keys & Backup</h2>
        <p className="text-gray-600">Manage your encryption keys and backups</p>
      </div>

      {!user?.hasBackup && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            You haven't backed up your keys yet. Without a backup, the Share function may be limited and you won't be able to recover your account if you lose access.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Public Keys</CardTitle>
          <CardDescription>Your public keys for encryption and identification</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Ethereum Address</Label>
            <div className="flex gap-2">
              <Input value={user?.address || ''} disabled className="flex-1 font-mono text-sm" />
              <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(user?.address || ''); toast.success('Address copied'); }}>
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label>RSA Public Key (SPKI PEM)</Label>
            <div className="relative">
              <textarea value={isLoadingKeys ? 'Loading…' : publicPem} disabled className="w-full h-32 p-3 text-xs font-mono bg-gray-50 border border-gray-200 rounded resize-none" />
              <Button variant="ghost" size="sm" className="absolute top-2 right-2" onClick={() => { navigator.clipboard.writeText(publicPem); toast.success('Public key copied'); }} disabled={!publicPem}>
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={handlePublishKeyCard} disabled={publishBusy} className="gap-2">
              {publishBusy ? 'Publishing…' : 'Publish My Key Card'}
            </Button>
            {publishCid && (
              <div className="text-sm text-gray-600">
                CID: <code className="bg-gray-100 px-1 py-0.5 rounded">{publishCid}</code>
                {publishUrl && (
                  <>
                    {' '}
                    <a href={publishUrl} target="_blank" rel="noreferrer" className="underline">Open</a>
                  </>
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Backup & Restore</CardTitle>
          <CardDescription>Download or restore your encrypted key backup</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="backupPassword">Backup Password</Label>
              <Input id="backupPassword" type="password" value={backupPassword} onChange={(e) => setBackupPassword(e.target.value)} placeholder="Use a strong password (>= 12 chars)" />
            </div>
          </div>
          <div className="flex gap-3">
            <Button onClick={handleDownloadBackup} className="gap-2" disabled={backupBusy}>
              <Download className="h-4 w-4" />
              {backupBusy ? 'Preparing…' : 'Download Backup (.dfspkey)'}
            </Button>

            <input ref={fileInputRef} type="file" accept=".dfspkey" onChange={handleFileSelect} className="hidden" />
            <Button variant="outline" onClick={() => fileInputRef.current?.click()} className="gap-2">
              <Upload className="h-4 w-4" />
              Restore from Backup
            </Button>
          </div>

          {showPasswordPrompt && selectedFile && (
            <div className="p-4 border border-gray-200 rounded-lg space-y-4 bg-gray-50">
              <div>
                <p className="text-sm mb-2">Selected file: {selectedFile.name}</p>
                <Label htmlFor="restorePassword">Password</Label>
                <Input id="restorePassword" type="password" value={restorePassword} onChange={(e) => setRestorePassword(e.target.value)} disabled={isRestoring} placeholder="Enter your password to decrypt" />
              </div>

              {error && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <div className="flex gap-2">
                <Button onClick={handleRestore} disabled={isRestoring || !restorePassword}>
                  {isRestoring ? 'Restoring...' : 'Restore Keys'}
                </Button>
                <Button variant="outline" onClick={() => { setShowPasswordPrompt(false); setSelectedFile(null); setRestorePassword(''); setError(''); }} disabled={isRestoring}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function SecuritySettings() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const getPasswordStrength = (): 'weak' | 'medium' | 'strong' | null => {
    if (!newPassword) return null;
    if (newPassword.length < 12) return 'weak';
    const hasUpper = /[A-Z]/.test(newPassword);
    const hasLower = /[a-z]/.test(newPassword);
    const hasDigit = /\d/.test(newPassword);
    const hasSpecial = /[^A-Za-z0-9]/.test(newPassword);
    const score = [hasUpper, hasLower, hasDigit, hasSpecial].filter(Boolean).length;
    if (score >= 3 && newPassword.length >= 16) return 'strong';
    if (score >= 2 && newPassword.length >= 12) return 'medium';
    return 'weak';
  };

  const passwordStrength = getPasswordStrength();
  const passwordsMatch = newPassword && confirmPassword && newPassword === confirmPassword;

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      setError('All fields are required');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match');
      return;
    }
    if (newPassword.length < 12) {
      setError('Password must be at least 12 characters');
      return;
    }
    setIsProcessing(true);
    setError('');
    setSuccess(false);
    try {
      // TODO: re-encrypt local keys with new password
      await new Promise(resolve => setTimeout(resolve, 1000));
      setSuccess(true);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      toast.success('Password changed successfully');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change password');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2>Security Settings</h2>
        <p className="text-gray-600">Change your encryption password</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Change Password</CardTitle>
          <CardDescription>
            Update the password used to encrypt your local private keys
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              Changing your password will re-encrypt your local private keys. Make sure to update your backup after changing your password.
            </AlertDescription>
          </Alert>

          <div className="space-y-2">
            <Label htmlFor="currentPassword">Current Password</Label>
            <Input id="currentPassword" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} disabled={isProcessing} placeholder="Enter your current password" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="newPassword">New Password</Label>
            <Input id="newPassword" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} disabled={isProcessing} placeholder="Enter new password" />
            {newPassword && passwordStrength && (
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Progress value={passwordStrength === 'weak' ? 33 : passwordStrength === 'medium' ? 66 : 100} className="h-1.5" />
                  <span className={`text-xs ${passwordStrength === 'weak' ? 'text-red-600' : passwordStrength === 'medium' ? 'text-yellow-600' : 'text-green-600'}`}>
                    {passwordStrength.charAt(0).toUpperCase() + passwordStrength.slice(1)}
                  </span>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm New Password</Label>
            <Input id="confirmPassword" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} disabled={isProcessing} placeholder="Confirm new password" />
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

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert>
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-800">Password changed successfully</AlertDescription>
            </Alert>
          )}

          <div className="flex justify-end">
            <Button onClick={handleChangePassword} disabled={isProcessing || !passwordsMatch || !currentPassword}>
              {isProcessing ? 'Processing...' : 'Change Password'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Layout
      children={(
        <div className="grid grid-cols-4 gap-6">
          <div className="col-span-1">
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <h3 className="mb-4">Settings</h3>
              <SettingsNav />
            </div>
          </div>
          <div className="col-span-3">
            <Outlet />
          </div>
        </div>
      )}
    />
  );
}
