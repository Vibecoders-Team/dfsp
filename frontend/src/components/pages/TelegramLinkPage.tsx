import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { CheckCircle2, Loader2, AlertTriangle, ArrowLeft } from 'lucide-react';
import { completeTelegramLink } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';

type Status = 'pending' | 'success' | 'error';

export default function TelegramLinkPage() {
  const location = useLocation();
  const [status, setStatus] = useState<Status>('pending');
  const [message, setMessage] = useState<string>('Linking account to Telegram...');

  const linkToken = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('token') || '';
  }, [location.search]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!linkToken) {
        setStatus('error');
        setMessage('Link does not contain a token for linking.');
        return;
      }

      try {
        setStatus('pending');
        setMessage('Linking account to Telegram...');
        await completeTelegramLink(linkToken);
        if (cancelled) return;
        setStatus('success');
        setMessage('Telegram successfully linked to your account.');
      } catch (err) {
        if (cancelled) return;
        setStatus('error');
        setMessage(getErrorMessage(err, 'Failed to complete Telegram linking.'));
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [linkToken]);

  const renderIcon = () => {
    if (status === 'pending') return <Loader2 className="h-5 w-5 animate-spin text-blue-600" />;
    if (status === 'success') return <CheckCircle2 className="h-5 w-5 text-green-600" />;
    return <AlertTriangle className="h-5 w-5 text-amber-600" />;
  };

  return (
    <Layout>
      <div className="max-w-xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          {renderIcon()}
          <div>
            <h1 className="text-xl font-semibold">Telegram linking</h1>
            <p className="text-gray-600 text-sm">You can close this window after successful linking.</p>
          </div>
        </div>

        <Alert variant={status === 'error' ? 'destructive' : undefined}>
          <AlertDescription className="flex items-center gap-3">
            {renderIcon()}
            <span>{message}</span>
          </AlertDescription>
        </Alert>

        <div className="flex gap-3">
          <Button asChild variant="outline">
            <Link to="/files">
              <ArrowLeft className="h-4 w-4" />
              Back to files
            </Link>
          </Button>
        </div>
      </div>
    </Layout>
  );
}
