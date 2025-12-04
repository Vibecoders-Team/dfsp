import axios, { InternalAxiosRequestConfig, isAxiosError, AxiosHeaders, AxiosResponse } from "axios";
import type {TypedDataDomain, TypedDataField} from "ethers";
import type {LoginMessage} from "./keychain";
import { ensureEOA, ensureRSA } from "./keychain";
import { findKey } from "./pubkeys";
import { saveKey } from "./pubkeys";
import { getAgent } from "./agent/manager"; // normalized quotes


// export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE });

const API_BASE = (import.meta as unknown as { env?: Record<string,string> }).env?.VITE_API_BASE ?? "/api";
export const ACCESS_TOKEN_KEY = "ACCESS_TOKEN";

export const api = axios.create({baseURL: API_BASE});

/** ---- Auth header interceptor (без any) ---- */
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const tok = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (tok) {
        // Превращаем headers в AxiosHeaders и ставим Authorization
        const headers = AxiosHeaders.from(config.headers);
        headers.set("Authorization", `Bearer ${tok}`);
        config.headers = headers;
    }
    return config;
});

/** ---- 401/403 handler ---- */
api.interceptors.response.use(
    (r: AxiosResponse) => r,
    (err: unknown) => {
        if (isAxiosError(err)) {
            const status = err.response?.status;
            const url = err.config?.url || '';
            // Do not redirect for public endpoints (we need to show TTL/limit/revoked errors)
            const isPublic = /\/public\//.test(url || '') || url.startsWith('/public/');
            if ((status === 401 || status === 403) && !isPublic) {
                try { localStorage.removeItem(ACCESS_TOKEN_KEY); } catch {/* ignore */}
                window.location.href = "/login";
            }
        }
        return Promise.reject(err);
    }
);

/** ---- Types ---- */
export type ChallengeOut = { challenge_id: string; nonce: `0x${string}`; exp_sec: number };
export type Tokens = { access: string; refresh: string };
export type TonChallenge = { challenge_id: string; nonce: string; exp_sec: number };
export type TonSignPayload =
  | { type: "binary"; bytes: string }
  | { type: "text"; text: string }
  | { type: "cell"; cell: string; schema: string };

export type HealthOut = {
    ok: boolean;
    api: { ok: boolean; version?: string; error?: string };
    db: { ok: boolean; error?: string };
    redis: { ok: boolean; error?: string };
    chain: { ok: boolean; chainId?: number; error?: string };
    contracts: { ok: boolean; names?: string[]; error?: string };
    ipfs: { ok: boolean; id?: string; error?: string };
};

export type StoreFileOut = { id_hex: `0x${string}`; cid: string; tx_hash: string; url: string };
export type CidOut = { cid: string; url: string };
export type MetaOut = {
    owner: string;
    cid: string;
    checksum: string;
    size: number;
    mime: string;
    name?: string;
    createdAt?: number;
};
export type VersionsOut = {
    versions: Array<{
        owner?: string; cid?: string; checksum?: string; size?: number; mime?: string; createdAt?: number;
    }>;
};
export type HistoryParams = {
    owner?: string;
    type?: "FileRegistered" | "FileVersioned";
    from_block?: number;
    to_block?: number;
    order?: "asc" | "desc";
    limit?: number;
};
export type HistoryOut = {
    items: Array<{
        type: string;
        blockNumber: number;
        txHash: string;
        timestamp: number;
        owner?: string;
        cid?: string;
        checksum?: string;
        size?: number;
        mime?: string;
    }>;
};

/** общий тип для EIP-712 блока, который ты отправляешь на бэк */
export type TypedLoginData = {
    domain: TypedDataDomain;
    types: Record<string, TypedDataField[]>;
    primaryType: "LoginChallenge";
    message: LoginMessage;
};
export type RegisterPayload = {
    challenge_id: string;
    eth_address: `0x${string}`;
    rsa_public: string;
    display_name: string;
    typed_data: TypedLoginData;
    signature: string;
};
export type LoginPayload = {
    challenge_id: string;
    eth_address: `0x${string}`;
    typed_data: TypedLoginData;
    signature: string;
};
export type ForwardTyped = {
  domain: Record<string, unknown>;
  types: Record<string, TypedDataField[]>;
  primaryType: string;
  message: Record<string, unknown>;
};

// /** ---- API calls ---- */
export async function fetchHealth() {
    const {data} = await api.get<HealthOut>("/health");
    return data;
}

export async function postChallenge() {
    const {data} = await api.post<ChallengeOut>("/auth/challenge");
    return data;
}

export async function postRegister(payload: RegisterPayload) {
    const {data} = await api.post<Tokens>("/auth/register", payload);
    return data;
}

export async function postTonChallenge(pubkeyB64: string) {
  const { data } = await api.post<TonChallenge>("/auth/ton/challenge", { pubkey: pubkeyB64 });
  return data;
}

export async function postTonLogin(payload: {
  challenge_id: string;
  signature: string;
  domain: string;
  timestamp: number;
  payload: TonSignPayload;
  address: string;
}) {
  const { data } = await api.post<Tokens>("/auth/ton/login", payload);
  return data;
}

export async function postLogin(payload: LoginPayload) {
    const {data} = await api.post<Tokens>("/auth/login", payload);
    return data;
}

export async function completeTelegramLink(linkToken: string) {
    const { data } = await api.post<{ ok: boolean }>("/tg/link-complete", { link_token: linkToken });
    return data;
}

export async function storeFile(file: File, idHex?: string) {
    const fd = new FormData();
    fd.append("file", file);
    if (idHex) fd.append("id_hex", idHex);
    const {data} = await api.post<StoreFileOut>("/storage/store", fd);
    return data;
}

export async function fetchCid(idHex: string) {
    const {data} = await api.get<CidOut>(`/storage/cid/${idHex}`);
    return data;
}

export async function fetchMeta(idHex: string) {
    const {data} = await api.get<MetaOut>(`/storage/meta/${idHex}`);
    return data;
}

export async function fetchVersions(idHex: string) {
    const {data} = await api.get<VersionsOut>(`/storage/versions/${idHex}`);
    return data;
}

export async function fetchHistory(idHex: string, params?: HistoryParams) {
    const {data} = await api.get<HistoryOut>(`/storage/history/${idHex}`, {params});
    return data;
}

// === Share & Grants API ===

export type Grant = {
  grantee: string;
  capId: string;
  maxDownloads: number;
  usedDownloads: number;
  expiresAt: string; // ISO
  status: "queued" | "pending" | "confirmed" | "revoked" | "expired" | "exhausted";
};

export type SharePayload = {
  users: string[];
  ttl_days: number;
  max_dl: number;
  encK_map: Record<string, string>;
  request_id: string;
};

export type ShareItem = { grantee: string; capId: string; status: Grant["status"] };
export type ShareOutResp = { items: ShareItem[]; typedDataList?: ForwardTyped[] };

export async function fetchGranteePubKey(addr: string): Promise<string> {
  const a = addr.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(a)) throw new Error("Invalid address format"); // address regex intact

  // Determine caller address depending on agent kind (avoid local EOA unlock for external wallets)
  let me: string;
  try {
    const agent = await getAgent();
    if (agent.kind === 'local') {
      me = (await ensureEOA()).address;
    } else {
      me = await agent.getAddress();
    }
  } catch {
    // Fallback to local ensureEOA if agent retrieval fails
    me = (await ensureEOA()).address;
  }

  // self-share: my address -> local PEM from IndexedDB
  if (a.toLowerCase() === me.toLowerCase()) {
    const { publicPem } = await ensureRSA();
    return publicPem;
  }

  // чужой адрес -> ищем в локальном каталоге
  const pem = findKey(a);
  if (pem) return pem;

  // нет локально — пытаемся получить с бэка и закешировать
  try {
    const { data } = await api.get<{ address: string; rsa_public: string; display_name?: string }>(`/users/${a}/pubkey`);
    if (data?.rsa_public) {
      saveKey(a, data.rsa_public);
      return data.rsa_public;
    }
  } catch (err: unknown) {
    // если 404 — оставим как PUBLIC_PEM_NOT_FOUND; остальные ошибки прокинем наружу
    if (isAxiosError(err) && err.response?.status === 404) {
      // fall-through
    } else {
      throw err;
    }
  }

  // источника нет — дальше перехватим в UI и предложим импорт
  throw new Error("PUBLIC_PEM_NOT_FOUND");
}

export async function listGrants(fileId: string): Promise<Grant[]> {
  // Avoid hitting backend when unauthenticated (e.g., after logout route switch)
  try {
    const tok = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (!tok) return [];
  } catch { /* ignore */ }
  try {
    const { data } = await api.get<{ items: Grant[] }>(`/files/${fileId}/grants`);
    return data.items;
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      if (e.response?.status === 404) return [];
    }
    throw e;
  }
}

export async function shareFile(
  fileId: string,
  payload: SharePayload,
  powHeader?: string
): Promise<ShareOutResp> {
  const { data } = await api.post<ShareOutResp>(
    `/files/${fileId}/share`,
    payload,
    { headers: powHeader ? { "X-PoW-Token": powHeader } : undefined }
  );
  return data;
}

export async function revokeGrant(capId: string): Promise<void> {
  await api.post(`/grants/${capId}/revoke`, {});
}

// === Download (by capId) ===

export type DownloadOut = { encK: string; ipfsPath: string; requestId?: string; typedData?: ForwardTyped; fileName?: string };

export async function fetchDownload(capId: string, powHeader?: string): Promise<DownloadOut> {
  const { data } = await api.get<DownloadOut>(`/download/${capId}`, {
    headers: powHeader ? { "X-PoW-Token": powHeader } : undefined,
  });
  return data;
}

// === Meta-tx submit ===
export async function submitMetaTx(requestId: string, typedData: ForwardTyped, signature: string): Promise<{ status: string; task_id?: string }>{
  const { data } = await api.post<{ status: string; task_id?: string }>(`/meta-tx/submit`, {
    request_id: requestId,
    typed_data: typedData,
    signature,
  });
  return data;
}

// === Revoke prepare (returns typedData) ===
export async function prepareRevoke(capId: string): Promise<{ status: string; requestId: string; typedData: ForwardTyped }>{
  const { data } = await api.post<{ status: string; requestId: string; typedData: ForwardTyped }>(`/grants/${capId}/revoke`, {});
  return data;
}

// === PoW Challenge ===
export type PowChallenge = { challenge: string; difficulty: number; ttl: number };

export async function requestPowChallenge(): Promise<PowChallenge> {
  const { data } = await api.post<PowChallenge>("/pow/challenge");
  return data;
}

// === Grant status polling ===
export type GrantStatus = {
  capId: string;
  grantee?: string;
  maxDownloads: number;
  usedDownloads: number;
  status: "queued" | "pending" | "confirmed" | "revoked" | "expired" | "exhausted";
  expiresAt?: string;
};

export async function fetchGrantByCapId(capId: string): Promise<GrantStatus> {
  const { data } = await api.get<GrantStatus>(`/grants/${capId}`);
  return data;
}

// === Files List ===
export type FileListItem = {
  id: string;
  name: string;
  size: number;
  mime: string;
  cid: string;
  checksum: string;
  created_at: string;
};

export async function fetchMyFiles(): Promise<FileListItem[]> {
  const { data } = await api.get<FileListItem[]>("/files");
  return data;
}

// === Grants list (current user) ===
export type MyGrantItem = {
  fileId: string;
  fileName?: string;
  capId: string;
  grantor: string; // UUID
  grantee: string; // UUID
  maxDownloads: number;
  usedDownloads: number;
  status: "queued" | "pending" | "confirmed" | "revoked" | "expired" | "exhausted";
  expiresAt: string; // ISO
  grantorAddr?: string; // optional, if backend later includes it
  granteeAddr?: string; // optional
};

export async function fetchMyGrants(role: "received" | "granted" = "received"): Promise<MyGrantItem[]> {
  const { data } = await api.get<{ items: MyGrantItem[] }>(`/grants`, { params: { role } });
  return data.items || [];
}

export async function storeEncrypted(
  file: Blob,
  opts: { idHex: string; checksum: string; plainSize: number; filename?: string; origName?: string; origMime?: string }
) {
    const fd = new FormData();
    fd.append('file', file, opts.filename || 'encrypted.bin');
    fd.append('id_hex', opts.idHex);
    fd.append('checksum', opts.checksum);
    fd.append('plain_size', String(opts.plainSize));
    if (opts.origName) fd.append('orig_name', opts.origName);
    if (opts.origMime) fd.append('orig_mime', opts.origMime);
    const { data } = await api.post<StoreFileOut>('/storage/store', fd);
    return data;
}

// === Action intents (handoff) ===
export type IntentConsumeOut = { ok: boolean; action: string | null; payload: Record<string, unknown> | null };

export async function consumeIntent(intentId: string): Promise<IntentConsumeOut> {
  const { data } = await api.post<IntentConsumeOut>(`/intents/${intentId}/consume`);
  return data;
}

// === Public Links API ===
export type PublicLinkPolicy = { max_downloads?: number; pow_difficulty?: number; one_time: boolean };
export type CreatePublicLinkResp = { token: string; expires_at: string; policy: PublicLinkPolicy };
export type CreatePublicLinkPayload = {
  version?: number;
  ttl_sec?: number;
  max_downloads?: number;
  pow?: { enabled: boolean; difficulty?: number };
  name_override?: string;
  mime_override?: string;
};

export async function createPublicLink(fileIdHex: string, payload: CreatePublicLinkPayload): Promise<CreatePublicLinkResp> {
  const { data } = await api.post<CreatePublicLinkResp>(`/files/${fileIdHex}/public-links`, payload);
  return data;
}

export type PublicMetaResp = {
  name: string;
  size?: number;
  mime?: string;
  cid?: string;
  fileId: string;
  version?: number;
  expires_at?: string;
  policy: Record<string, unknown>;
};

export async function fetchPublicMeta(token: string): Promise<PublicMetaResp> {
  const { data } = await api.get<PublicMetaResp>(`/public/${token}/meta`);
  return data;
}

export async function submitPow(token: string, nonce: string, solution: string): Promise<{ ok: true }>{
  const { data } = await api.post<{ ok: true }>(`/public/${token}/pow`, { nonce, solution });
  return data;
}

export async function fetchPublicContent(token: string): Promise<Blob> {
  const res = await api.get(`/public/${token}/content`, { responseType: 'blob' });
  return res.data as Blob;
}

export async function revokePublicLink(token: string): Promise<{ revoked: true }>{
  const { data } = await api.delete<{ revoked: true }>(`/public-links/${token}`);
  return data;
}

export type PublicLinkItem = { token: string; expires_at?: string; policy?: PublicLinkPolicy; downloads_count?: number };
export async function listPublicLinks(fileIdHex: string): Promise<PublicLinkItem[]>{
  try {
    const { data } = await api.get<{ items: PublicLinkItem[] }>(`/files/${fileIdHex}/public-links`);
    return data.items || [];
  } catch (e) {
    if (isAxiosError(e) && (e.response?.status === 404 || e.response?.status === 401)) return [];
    throw e;
  }
}
