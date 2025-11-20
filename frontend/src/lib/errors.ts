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
    // Wallets (MetaMask) may wrap rejection differently; attempt to normalize
    if (/ACTION_REJECTED|user rejected/i.test(msg)) return 'Signature request was cancelled';
    return msg;
  }
  return fallback;
}
