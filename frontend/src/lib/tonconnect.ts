let tonUI: any = null;

export function buildFallbackManifest() {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env || {};
  const appUrl = env.TONCONNECT_APP_URL || env.VITE_TONCONNECT_APP_URL || env.VITE_PUBLIC_ORIGIN || env.PUBLIC_WEB_ORIGIN || (typeof window !== 'undefined' ? window.location.origin : '');
  const icon = env.TONCONNECT_ICON_URL || env.VITE_TONCONNECT_ICON_URL || env.VITE_PUBLIC_ICON || '/vite.svg';
  const terms = env.TONCONNECT_TERMS_URL || `${appUrl.replace(/\/$/, '')}/terms`;
  return {
    url: appUrl || '',
    name: env.TONCONNECT_APP_NAME || env.VITE_APP_NAME || 'DFSP',
    iconUrl: icon,
    termsOfUseUrl: terms,
  } as const;
}

// (fetchManifestWithFallback removed — not used; fallback handled via blob manifest in getTonConnect)

export function getTonConnect(): any {
  if (typeof window === "undefined") {
    throw new Error("TonConnect unavailable in SSR");
  }
  if (!tonUI) {
    // Use real HTTPS URL for manifest to comply with Telegram WebApp CSP
    // CSP from Telegram only allows 'self' and https: in connect-src
    const manifestUrl = `${window.location.origin}/tonconnect-manifest.json`;
    console.info('[TonConnect] Using manifest URL:', manifestUrl);
    // Lazy load TonConnectUI
    const mod = require('@tonconnect/ui');
    const TonConnectUI = (mod && mod.TonConnectUI) || mod?.default;
    tonUI = new TonConnectUI({
      manifestUrl,
      actionsConfiguration: {
        notifications: ["before", "success", "error"],
        modals: ["before", "success", "error"],
      },
    });
  }
  return tonUI;
}

export function hexToBytes(hex: string): Uint8Array {
  const clean = hex.startsWith("0x") ? hex.slice(2) : hex;
  if (clean.length % 2 !== 0) throw new Error("Hex length must be even");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < clean.length; i += 2) {
    out[i / 2] = parseInt(clean.slice(i, i + 2), 16);
  }
  return out;
}

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

export async function deriveEthFromTonPub(pubkeyHex: string): Promise<string> {
  const { ethers } = await import('ethers');
  const hex = pubkeyHex.startsWith('0x') ? pubkeyHex : `0x${pubkeyHex}`;
  const hash = ethers.keccak256(hex);
  return `0x${hash.slice(-40)}`;
}
