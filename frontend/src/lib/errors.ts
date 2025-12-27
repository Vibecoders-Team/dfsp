// Унифицированный текст ошибки для UI
import { isAxiosError } from "axios";

type ApiErrorBody = { detail?: unknown } | unknown;

export function getErrorMessage(e: unknown, fallback = "Request failed"): string {
  if (isAxiosError(e)) {
    const data = e.response?.data as ApiErrorBody | undefined;
    let detail: unknown;
    if (data && typeof data === 'object' && 'detail' in data) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      detail = (data as any).detail;
    }
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (e.response?.status === 404) return 'Not found';
    if (e.response?.status === 401) return 'Unauthorized';
    if (e.response?.status === 403) return 'Forbidden';
    if (e.message) return e.message;
  }
  if (e instanceof Error && e.message) {
    const msg = e.message;
    if (msg === 'unlock_cancelled') return 'Unlock was cancelled — enter your password in the dialog and try again.';
    if (/^EOA locked/i.test(msg)) return 'Local key is locked — unlock to continue.';
    if (/Signature request was cancelled/i.test(msg)) return 'Signature request was cancelled';

    // TON Connect specific error handling
    if (/TON login was cancelled/i.test(msg)) return 'TON login was cancelled';
    if (/Wallet connection was cancelled/i.test(msg)) return 'Wallet connection was cancelled';
    if (/Signing was cancelled/i.test(msg)) return 'Transaction signing was cancelled';
    if (/TON_CONNECT_SDK_ERROR.*Wallet was not connected/i.test(msg)) return 'Wallet connection was cancelled';
    if (/Failed to connect wallet/i.test(msg)) return 'Failed to connect wallet';
    if (/Failed to sign challenge/i.test(msg)) return 'Failed to sign authentication challenge';

    // Wallets (MetaMask) may wrap rejection differently; attempt to normalize
    if (/ACTION_REJECTED|user rejected/i.test(msg)) return 'Signature request was cancelled';
    return msg;
  }
  return fallback;
}
