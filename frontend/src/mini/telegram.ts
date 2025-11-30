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
  // Prefer the raw initData from Telegram WebApp (already a query string). Do NOT decode/encode it.
  const rawInitData = window.Telegram?.WebApp?.initData;
  if (rawInitData) return rawInitData;

  // Fallbacks: some clients can pass tgWebAppData in query/hash; keep raw value to preserve signature.
  const search = new URLSearchParams(window.location.search);
  const queryInit = search.get("tgWebAppData");
  if (queryInit) return queryInit;

  const hashParams = window.location.hash.startsWith("#")
    ? new URLSearchParams(window.location.hash.slice(1))
    : null;
  const hashInit = hashParams?.get("tgWebAppData");
  if (hashInit) return hashInit;

  return null;
}

export function markWebAppReady() {
  try {
    window.Telegram?.WebApp?.ready?.();
  } catch {
    /* noop */
  }
}
