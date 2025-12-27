import axios, { AxiosHeaders, isAxiosError } from "axios";

export type WebAppAuthResponse = { session: string; exp: number };

const API_BASE = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE ?? "/api";
export const MINI_SESSION_KEY = "TG_WEBAPP_SESSION";
const MINI_ERROR_HEADER = "x-dfsp-error";

let sessionToken: string | null =
  typeof sessionStorage !== "undefined" ? sessionStorage.getItem(MINI_SESSION_KEY) : null;

export function setMiniSession(token: string | null) {
  sessionToken = token;
  try {
    if (token) {
      sessionStorage.setItem(MINI_SESSION_KEY, token);
    } else {
      sessionStorage.removeItem(MINI_SESSION_KEY);
    }
  } catch {
    /* ignore storage failures */
  }
}

export function getMiniSession() {
  return sessionToken;
}

export const miniApi = axios.create({ baseURL: API_BASE });

miniApi.interceptors.request.use((config) => {
  const tok = getMiniSession();
  if (tok) {
    const headers = AxiosHeaders.from(config.headers);
    headers.set("Authorization", `Bearer ${tok}`);
    config.headers = headers;
  }
  return config;
});

miniApi.interceptors.response.use(
  (r) => r,
  (err) => {
    const normalized = normalizeMiniError(err);
    if (normalized.status === 401 || normalized.status === 403) {
      setMiniSession(null);
    }
    return Promise.reject(normalized);
  }
);

export async function authenticateWithInitData(initData: string): Promise<WebAppAuthResponse> {
  const { data } = await miniApi.post<WebAppAuthResponse>("/tg/webapp/auth", { initData });
  return data;
}

export class MiniApiError extends Error {
  status?: number;
  code?: string;
  constructor(message: string, opts?: { status?: number; code?: string }) {
    super(message);
    this.status = opts?.status;
    this.code = opts?.code;
  }
}

export function normalizeMiniError(err: unknown): MiniApiError {
  if (err instanceof MiniApiError) return err;
  if (isAxiosError(err)) {
    const status = err.response?.status;
    const code = err.response?.headers?.[MINI_ERROR_HEADER] as string | undefined;
    const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof err.message === "string"
          ? err.message
          : "Request failed";
    return new MiniApiError(message, { status, code });
  }
  if (err instanceof Error) return new MiniApiError(err.message);
  return new MiniApiError("Unknown error");
}

export async function miniGet<T>(url: string, init?: Parameters<typeof miniApi.get>[1]) {
  ensureSession();
  const { data } = await miniApi.get<T>(url, init);
  return data;
}

export async function miniPost<T>(url: string, body?: unknown, init?: Parameters<typeof miniApi.post>[2]) {
  ensureSession();
  const { data } = await miniApi.post<T>(url, body, init);
  return data;
}

function ensureSession() {
  if (!getMiniSession()) {
    throw new MiniApiError("Нет webapp сессии", { status: 401 });
  }
}

export type MiniFileListItem = {
  id: string;
  name: string;
  size: number;
  mime: string;
  cid: string;
  checksum: string;
  created_at: string;
};

export type MiniGrantItem = {
  grantee: string;
  capId: string;
  maxDownloads: number;
  usedDownloads: number;
  expiresAt: string;
  status: "queued" | "pending" | "confirmed" | "revoked" | "expired" | "exhausted";
};

export async function miniListFiles(): Promise<MiniFileListItem[]> {
  return miniGet<MiniFileListItem[]>("/files");
}

export async function miniListFileGrants(fileId: string): Promise<MiniGrantItem[]> {
  const data = await miniGet<{ items: MiniGrantItem[] }>(`/files/${fileId}/grants`);
  return data.items || [];
}

export type MiniIntentCreateResponse = { intent_id: string; url: string; ttl: number };

export async function miniCreateIntent(
  action: "share" | "revoke" | "delete_file",
  payload: Record<string, unknown>
): Promise<MiniIntentCreateResponse> {
  return miniPost<MiniIntentCreateResponse>("/intents", { action, payload });
}

export type MiniTonChallenge = { challenge_id: string; nonce: string; exp_sec: number };

export async function miniTonChallenge(pubkeyB64: string): Promise<MiniTonChallenge> {
  const { data } = await miniApi.post<MiniTonChallenge>("/auth/ton/challenge", { pubkey: pubkeyB64 });
  return data;
}

export type MiniTonLoginOut = { access: string; refresh: string };
export type MiniTonSignPayload =
  | { type: "binary"; bytes: string }
  | { type: "text"; text: string }
  | { type: "cell"; cell: string; schema: string };

export async function miniTonLogin(payload: {
  challenge_id: string;
  signature: string;
  domain: string;
  timestamp: number;
  payload: MiniTonSignPayload;
  address: string; // добавлено поле адреса TON
}): Promise<MiniTonLoginOut> {
  const { data } = await miniApi.post<MiniTonLoginOut>("/auth/ton/login", payload);
  return data;
}

export async function miniUpdateRsaPublic(rsaPublic: string): Promise<{ ok: boolean; address: string }> {
  const { data } = await miniApi.put<{ ok: boolean; address: string }>("/users/me/rsa-public", { rsa_public: rsaPublic });
  return data;
}

export type MiniVerifyMeta = {
  cid: string;
  checksum: string;
  size: number;
  mime: string | null;
  name?: string | null;
};

export type MiniVerifyResponse = {
  onchain: MiniVerifyMeta | null;
  offchain: MiniVerifyMeta | null;
  match: boolean;
};

export async function miniVerify(fileId: string): Promise<MiniVerifyResponse> {
  return miniGet<MiniVerifyResponse>(`/verify/${fileId}`);
}

// === Public Links API ===
export type MiniPublicLinkPolicy = { max_downloads?: number; pow_difficulty?: number; one_time: boolean };
export type MiniCreatePublicLinkPayload = {
  version?: number;
  ttl_sec?: number;
  max_downloads?: number;
  pow?: { enabled: boolean; difficulty?: number };
  name_override?: string;
  mime_override?: string;
};
export type MiniPublicLinkItem = {
  token: string;
  expires_at?: string;
  policy?: MiniPublicLinkPolicy;
  downloads_count?: number;
};
export type MiniPublicLinkCreateResp = { token: string; expires_at: string | null; policy: MiniPublicLinkPolicy };

export async function miniCreatePublicLink(fileId: string, payload: MiniCreatePublicLinkPayload): Promise<MiniPublicLinkCreateResp> {
  return miniPost<MiniPublicLinkCreateResp>(`/files/${fileId}/public-links`, payload);
}

export async function miniListPublicLinks(fileId: string): Promise<MiniPublicLinkItem[]> {
  try {
    const data = await miniGet<{ items: MiniPublicLinkItem[] }>(`/files/${fileId}/public-links`);
    return data.items || [];
  } catch (e) {
    if ((e as MiniApiError).status === 404) return [];
    throw e;
  }
}

export async function miniRevokePublicLink(token: string): Promise<{ revoked: boolean }> {
  return miniApi.delete<{ revoked: boolean }>(`/public-links/${token}`).then(r => r.data);
}

export type MiniPublicMetaResp = {
  name: string;
  size?: number;
  mime?: string;
  cid?: string;
  fileId: string;
  version?: number;
  expires_at?: string;
  policy: Record<string, unknown>;
};

export async function miniGetPublicMeta(token: string): Promise<MiniPublicMetaResp> {
  const { data } = await miniApi.get<MiniPublicMetaResp>(`/public/${token}/meta`);
  return data;
}

export async function miniGetPublicContent(token: string): Promise<Blob> {
  const res = await miniApi.get(`/public/${token}/content`, { responseType: 'blob' });
  return res.data as Blob;
}

export async function miniSubmitPow(token: string, nonce: string, solution: string): Promise<{ ok: boolean }> {
  const { data } = await miniApi.post<{ ok: boolean }>(`/public/${token}/pow`, { nonce, solution });
  return data;
}

export type MiniPowChallenge = { challenge: string; difficulty: number; ttl: number };

export async function miniRequestPowChallenge(): Promise<MiniPowChallenge> {
  const { data } = await miniApi.post<MiniPowChallenge>("/pow/challenge");
  return data;
}

// === Rename API ===
export type MiniRenameFileResp = {
  idHex: string;
  name: string;
  size: number;
  mime?: string;
  cid: string;
  checksum: string;
  createdAt: number;
};

export async function miniRenameFile(fileId: string, newName: string): Promise<MiniRenameFileResp> {
  return miniApi.patch<MiniRenameFileResp>(`/files/${fileId}`, { name: newName }).then(r => r.data);
}
