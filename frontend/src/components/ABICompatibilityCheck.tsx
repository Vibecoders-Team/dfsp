import { useEffect, useState } from 'react';
import { Alert, AlertDescription } from './ui/alert';
import { Button } from './ui/button';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * ABICompatibilityCheck component
 * Monitors for contract/ABI changes and displays warning when incompatibility detected
 * Prevents app crashes by prompting reload when contracts are updated
 */
export default function ABICompatibilityCheck() {
  const [incompatible, setIncompatible] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  useEffect(() => {
    // Listen for ABI incompatibility errors
    const handleABIError = (event: ErrorEvent) => {
      const message = event.message || event.error?.message || '';

      // Check for common ABI/contract incompatibility patterns
      if (
        message.includes('contract') ||
        message.includes('ABI') ||
        message.includes('function') && message.includes('not found') ||
        message.includes('revert') && message.includes('signature') ||
        message.includes('unknown selector')
      ) {
        console.warn('Detected possible ABI incompatibility:', message);
        setIncompatible(true);
      }
    };

    // Listen for global errors
    window.addEventListener('error', handleABIError);

    // Listen for unhandled promise rejections (common with web3 calls)
    const handleRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason?.message || String(event.reason);

      if (
        reason.includes('contract') ||
        reason.includes('ABI') ||
        reason.includes('function') && reason.includes('not found') ||
        reason.includes('unknown selector')
      ) {
        console.warn('Detected possible ABI incompatibility in promise:', reason);
        setIncompatible(true);
      }
    };

    window.addEventListener('unhandledrejection', handleRejection);

    // If we detect a new deployment, the backend could set a version header
    // For now, we'll rely on error detection

    return () => {
      window.removeEventListener('error', handleABIError);
      window.removeEventListener('unhandledrejection', handleRejection);
    };
  }, []);

  const handleReload = () => {
    setIsReloading(true);

    // Clear any cached contract data
    try {
      const keysToRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.includes('contract') || key.includes('abi'))) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));
    } catch (e) {
      console.warn('Failed to clear contract cache:', e);
    }

    // Reload the application
    window.location.reload();
  };

  const handleDismiss = () => {
    setIncompatible(false);
  };

  if (!incompatible) {
    return null;
  }

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-2xl w-full px-4">
      <Alert variant="destructive" className="border-amber-200 bg-amber-50">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertDescription className="text-amber-900">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-semibold mb-1">Contract Update Detected</p>
              <p className="text-sm">
                The smart contracts have been updated. Please reload the application to continue using it safely.
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <Button
                size="sm"
                onClick={handleReload}
                disabled={isReloading}
                className="bg-amber-600 hover:bg-amber-700 text-white"
              >
                <RefreshCw className="h-4 w-4 mr-1" />
                {isReloading ? 'Reloading...' : 'Reload'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleDismiss}
                className="border-amber-300"
              >
                Dismiss
              </Button>
            </div>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  );
}

