import { useState } from 'react';
import Layout from '../Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { Upload, AlertCircle, CheckCircle2, Key } from 'lucide-react';
import { useAuth } from '../useAuth';
import { toast } from 'sonner';
import { Link, useNavigate } from 'react-router-dom';
import type * as React from "react";

export default function RestorePage() {
  const { restoreAccount } = useAuth();
  const [file, setFile] = useState<File|null>(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  const onSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setFile(f || null);
    setError('');
  };

  const onRestore = async () => {
    if (!file) { setError('Please choose a .dfspkey file'); return; }
    if (!password) { setError('Please enter password'); return; }
    setBusy(true); setError(''); setSuccess(false);
    try {
      const res = await restoreAccount(file, password);
      setSuccess(true);
      if (res.mode === 'RSA-only') {
        toast.success('Keys restored. Login with your wallet to continue.');
        navigate('/login');
      } else {
        toast.success('Keys restored, signing in...');
        navigate('/files');
      }
    } catch (e) {
      const err = e as Error;
      setError(err?.message || 'Failed to restore from backup');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-lg mx-auto">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-3">
            <Key className="h-8 w-8 text-blue-600" />
          </div>
          <h1 className="mb-1">Restore from Backup</h1>
          <p className="text-gray-600 text-sm">Import your .dfspkey file and enter the password to recover access</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Backup File</CardTitle>
            <CardDescription>Only .dfspkey files created by DFSP are supported</CardDescription>
          </CardHeader>
          <form onSubmit={e => { e.preventDefault(); onRestore(); }}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="file">Choose file</Label>
              <Input id="file" type="file" accept=".dfspkey,application/json" onChange={onSelect} disabled={busy} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} placeholder="Backup password" disabled={busy} />
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
                <AlertDescription className="text-green-700">Restored successfully</AlertDescription>
              </Alert>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !file || !password} className="gap-2">
                <Upload className="h-4 w-4" />
                {busy ? 'Restoring…' : 'Restore & Sign In'}
              </Button>
              <Link to="/login" className="ml-auto">
                <Button type="button" variant="outline">Back to Login</Button>
              </Link>
            </div>
          </CardContent>
          </form>
        </Card>
      </div>
    </Layout>
  );
}
