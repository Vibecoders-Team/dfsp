import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { Link, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../useAuth';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Key, User, Download, Upload, AlertCircle, CheckCircle2, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { ensureRSA, createBackupBlob, createBackupBlobRSAOnly } from '@/lib/keychain.ts';
import { publishMyKeyCard } from '@/lib/publishMyKey.ts';
import { isEOAUnlocked } from '@/lib/keychain';

function SettingsNav() {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path || location.pathname.endsWith('/' + path);

  return (
    <nav className="space-y-1">
      <Link to="profile">
        <Button variant={isActive('profile') ? 'secondary' : 'ghost'} className="w-full justify-start gap-2">
          <User className="h-4 w-4" />
          Profile
        </Button>
      </Link>
      <Link to="keys">
        <Button variant={isActive('keys') ? 'secondary' : 'ghost'} className="w-full justify-start gap-2">
          <Key className="h-4 w-4" />
          Keys & Backup
        </Button>
      </Link>
      {/* Security page удалена */}
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
      if (!backupPassword || backupPassword.length < 8) {
        setError('Set a password (>= 8 chars) to encrypt your backup');
        return;
      }
      if (!isEOAUnlocked()) {
        toast.info('Unlock your local key first');
        window.dispatchEvent(new CustomEvent('dfsp:unlock-dialog'));
        return;
      }
      setBackupBusy(true);
      const blob = await createBackupBlob(backupPassword);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dfsp-backup-${Date.now()}.dfspkey`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
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
      const res = await restoreAccount(selectedFile, restorePassword);
      if (res.mode === 'RSA-only') {
        toast.success('RSA key restored. Use your external wallet on next login.');
      } else {
        toast.success('Keys restored successfully');
      }
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
              <Input id="backupPassword" type="password" value={backupPassword} onChange={(e) => setBackupPassword(e.target.value)} placeholder="Use a strong password (>= 8 chars)" />
            </div>
          </div>
          <div className="flex gap-3">
            <Button onClick={handleDownloadBackup} className="gap-2" disabled={backupBusy}>
              <Download className="h-4 w-4" />
              {backupBusy ? 'Preparing…' : 'Download Backup (.dfspkey)'}
            </Button>
            <Button variant="secondary" onClick={async()=>{
              try {
                if(!backupPassword || backupPassword.length < 8){ setError('Set a password (>= 8 chars)'); return; }
                if (!isEOAUnlocked()) { toast.info('Unlock your local key first'); window.dispatchEvent(new CustomEvent('dfsp:unlock-dialog')); return; }
                setBackupBusy(true);
                const blob = await createBackupBlobRSAOnly(backupPassword);
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a'); a.href = url; a.download = `dfsp-backup-rsa-${Date.now()}.dfspkey`; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
                toast.success('RSA-only backup downloaded');
              } catch(e){ setError(e instanceof Error ? e.message : 'Failed to create RSA-only backup'); }
              finally { setBackupBusy(false); }
            }} disabled={backupBusy}>
              <Download className="h-4 w-4" /> RSA-only
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

export default function SettingsPage() {
  return (
    <Layout children={(
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
    )} />
  );
}
