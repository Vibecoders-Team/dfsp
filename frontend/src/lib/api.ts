import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
export const api = axios.create({ baseURL: API_BASE });

// если включим guard позже — раскомментируй:
// api.interceptors.request.use((cfg) => {
//   const tok = localStorage.getItem("ACCESS_TOKEN");
//   if (tok) cfg.headers.Authorization = `Bearer ${tok}`;
//   return cfg;
// });

export type ChallengeOut = { challenge_id: string; nonce: `0x${string}`; exp_sec: number };
export type Tokens = { access: string; refresh: string };

export async function fetchHealth() {
  const { data } = await api.get("/health");
  return data as {
    ok: boolean;
    api: { ok: boolean; version?: string; error?: string };
    db: { ok: boolean; error?: string };
    redis: { ok: boolean; error?: string };
    chain: { ok: boolean; chainId?: number; error?: string };
    contracts: { ok: boolean; names?: string[]; error?: string };
    ipfs: { ok: boolean; id?: string; error?: string };
  };
}


export async function postChallenge() {
  const { data } = await api.post<ChallengeOut>("/auth/challenge");
  return data;
}
export async function postRegister(payload: any) {
  const { data } = await api.post<Tokens>("/auth/register", payload);
  return data;
}
export async function postLogin(payload: any) {
  const { data } = await api.post<Tokens>("/auth/login", payload);
  return data;
}

export async function storeFile(file: File, idHex?: string) {
  const fd = new FormData();
  fd.append("file", file);
  if (idHex) fd.append("id_hex", idHex);
  const { data } = await api.post("/storage/store", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data as { id_hex: string; cid: string; tx_hash: string; url: string };
}
export async function fetchCid(idHex: string) {
  const { data } = await api.get(`/storage/cid/${idHex}`);
  return data as { cid: string; url: string };
}
export async function fetchMeta(idHex: string) {
  const { data } = await api.get(`/storage/meta/${idHex}`);
  return data as {
    owner: string; cid: string; checksum: string; size: number; mime: string; createdAt: number;
  };
}
export async function fetchVersions(idHex: string) {
  const { data } = await api.get(`/storage/versions/${idHex}`);
  return data as { versions: Array<{
    owner?: string; cid?: string; checksum?: string; size?: number; mime?: string; createdAt?: number;
  }> };
}
export async function fetchHistory(idHex: string, params?: {
  owner?: string;
  type?: "FileRegistered"|"FileVersioned";
  from_block?: number;
  to_block?: number;
  order?: "asc"|"desc";
  limit?: number;
}) {
  const { data } = await api.get(`/storage/history/${idHex}`, { params });
  return data as { items: Array<{
    type: string; blockNumber: number; txHash: string; timestamp: number;
    owner?: string; cid?: string; checksum?: string; size?: number; mime?: string;
  }> };
}
