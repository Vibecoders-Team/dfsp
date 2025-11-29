declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData?: string;
        initDataUnsafe?: unknown;
        ready?: () => void;
      };
    };
  }
}

/**
 * Read Telegram initData from either window.Telegram.WebApp or URL params.
 * Telegram passes it as a raw query string; we keep it as-is for signature verification.
 */
export function readInitData(): string | null {
  const search = new URLSearchParams(window.location.search);
  const queryInit = search.get("tgWebAppData");
  if (queryInit) {
    try {
      return decodeURIComponent(queryInit);
    } catch {
      return queryInit;
    }
  }

  const hashParams = window.location.hash.startsWith("#")
    ? new URLSearchParams(window.location.hash.slice(1))
    : null;
  const hashInit = hashParams?.get("tgWebAppData");
  if (hashInit) {
    try {
      return decodeURIComponent(hashInit);
    } catch {
      return hashInit;
    }
  }

  return window.Telegram?.WebApp?.initData || null;
}

export function markWebAppReady() {
  try {
    window.Telegram?.WebApp?.ready?.();
  } catch {
    /* noop */
  }
}
