import axios, { InternalAxiosRequestConfig, isAxiosError, AxiosHeaders } from "axios";
import type {TypedDataDomain, TypedDataField} from "ethers";
import type {LoginMessage} from "./keychain";
import { ensureEOA, ensureRSA } from "./keychain";
import { findKey } from "./pubkeys";


// export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE });

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
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
    (r) => r,
    (err: unknown) => {
        if (isAxiosError(err)) {
            const status = err.response?.status;
            if (status === 401 || status === 403) {
                // например, редирект или логаут
                // window.location.href = "/login";
            }
        }
        return Promise.reject(err);
    }
);

/** ---- Types ---- */
export type ChallengeOut = { challenge_id: string; nonce: `0x${string}`; exp_sec: number };
export type Tokens = { access: string; refresh: string };

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
    createdAt: number;
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

/** ---- API calls ---- */
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

export async function postLogin(payload: LoginPayload) {
    const {data} = await api.post<Tokens>("/auth/login", payload);
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
  status: "pending" | "confirmed" | "revoked" | "expired";
};

export type SharePayload = {
  users: string[];
  ttl_days: number;
  max_dl: number;
  encK_map: Record<string, string>;
  request_id: string;
};

export type ShareItem = { grantee: string; capId: string; status: Grant["status"] };

export async function fetchGranteePubKey(addr: string): Promise<string> {
  const a = addr.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(a)) throw new Error("Invalid address format");

  // self-share: мой адрес -> локальный PEM из IndexedDB
  const me = (await ensureEOA()).address;
  if (a.toLowerCase() === me.toLowerCase()) {
    const { publicPem } = await ensureRSA();
    return publicPem;
  }

  // чужой адрес -> ищем в локальном каталоге
  const pem = findKey(a);
  if (pem) return pem;

  // источника нет — дальше перехватим в UI и предложим импорт
  throw new Error("PUBLIC_PEM_NOT_FOUND");
}

export async function listGrants(fileId: string): Promise<Grant[]> {
  try {
    const { data } = await api.get<{ items: Grant[] }>(`/files/${fileId}/grants`);
    return data.items;
  } catch (e) {
    // на бэке нет эндпоинта → просто вернём пустой список
    if (isAxiosError(e) && e.response?.status === 404) return [];
    throw e;
  }
}

export async function shareFile(
  fileId: string,
  payload: SharePayload,
  powHeader?: string
): Promise<ShareItem[]> {
  const { data } = await api.post<{ items: ShareItem[] }>(
    `/files/${fileId}/share`,
    payload,
    { headers: powHeader ? { "X-PoW": powHeader } : undefined }
  );
  return data.items;
}

export async function revokeGrant(capId: string): Promise<void> {
  await api.post(`/grants/${capId}/revoke`, {});
}

// === Download (by capId) ===

export type DownloadOut = { encK: string; ipfsPath: string };

export async function fetchDownload(capId: string, powHeader?: string): Promise<DownloadOut> {
  const { data } = await api.get<DownloadOut>(`/download/${capId}`, {
    headers: powHeader ? { "X-PoW": powHeader } : undefined,
  });
  return data;
}

// === Grant status polling ===

export type GrantStatus = {
  capId: string;
  grantee?: string;
  maxDownloads: number;
  usedDownloads: number;
  status: "pending" | "confirmed" | "revoked" | "expired" | "exhausted";
  expiresAt?: string;
};

export async function fetchGrantByCapId(capId: string): Promise<GrantStatus> {
  const { data } = await api.get<GrantStatus>(`/grants/${capId}`);
  return data;
}

// === PoW Challenge ===
export type PowChallenge = { challenge: string; difficulty: number; ttl: number };

export async function requestPowChallenge(): Promise<PowChallenge> {
  const { data } = await api.post<PowChallenge>("/pow/challenge");
  return data;
}
