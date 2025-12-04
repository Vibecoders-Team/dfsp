import { useEffect, useState } from 'react';
import { Button } from './ui/button';
import { Alert, AlertDescription } from './ui/alert';
import { RefreshCw } from 'lucide-react';

/**
 * UpdateNotification component
 * Monitors for application updates and displays a banner to reload
 * Prevents state loss by prompting user before reload
 */
export default function UpdateNotification() {
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [isReloading, setIsReloading] = useState(false);

  useEffect(() => {
    // Check for updates periodically (every 5 minutes)
    const checkForUpdates = async () => {
      try {
        // Check if the index.html has changed by comparing etags or timestamps
        const response = await fetch(window.location.origin + '/', {
          method: 'HEAD',
          cache: 'no-cache',
        });

        const currentEtag = sessionStorage.getItem('app-etag');
        const newEtag = response.headers.get('etag');

        if (currentEtag && newEtag && currentEtag !== newEtag) {
          setUpdateAvailable(true);
        } else if (!currentEtag && newEtag) {
          sessionStorage.setItem('app-etag', newEtag);
        }
      } catch (error) {
        console.debug('Update check failed:', error);
      }
    };

    // Initial check
    checkForUpdates();

    // Check every 5 minutes
    const interval = setInterval(checkForUpdates, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  const handleReload = () => {
    setIsReloading(true);

    // Save current state to sessionStorage for restoration after reload
    try {
      const currentPath = window.location.pathname + window.location.search + window.location.hash;
      sessionStorage.setItem('dfsp-reload-path', currentPath);
    } catch (e) {
      console.warn('Failed to save reload path:', e);
    }

    // Reload the page
    window.location.reload();
  };

  // Restore path after reload
  useEffect(() => {
    try {
      const savedPath = sessionStorage.getItem('dfsp-reload-path');
      if (savedPath && savedPath !== window.location.pathname + window.location.search + window.location.hash) {
        sessionStorage.removeItem('dfsp-reload-path');
        window.history.replaceState(null, '', savedPath);
      }
    } catch (e) {
      console.warn('Failed to restore path:', e);
    }
  }, []);

  if (!updateAvailable) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md">
      <Alert className="border-blue-200 bg-blue-50">
        <RefreshCw className="h-4 w-4 text-blue-600" />
        <AlertDescription className="flex items-center justify-between gap-4">
          <span className="text-sm text-blue-900">
            A new version is available. Please reload to update.
          </span>
          <Button
            size="sm"
            onClick={handleReload}
            disabled={isReloading}
            className="shrink-0"
          >
            {isReloading ? 'Reloading...' : 'Reload'}
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  );
}

