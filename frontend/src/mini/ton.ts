import { TonConnectUI } from "@tonconnect/ui";

let tonUI: TonConnectUI | null = null;

function resolveManifestUrl() {
  const envUrl = (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_TONCONNECT_MANIFEST;
  if (envUrl) return envUrl;
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin.replace(/\/+$/, "")}/tonconnect-manifest.json`;
  }
  return "/tonconnect-manifest.json";
}

export function getTonConnect(): TonConnectUI {
  if (typeof window === "undefined") {
    throw new Error("TonConnect unavailable in SSR");
  }
  if (!tonUI) {
    tonUI = new TonConnectUI({
      manifestUrl: resolveManifestUrl(),
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
