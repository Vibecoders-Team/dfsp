import axios, { AxiosHeaders, isAxiosError } from "axios";

export type WebAppAuthResponse = { session: string; exp: number };

const API_BASE = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE ?? "/api";
export const MINI_SESSION_KEY = "TG_WEBAPP_SESSION";

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
    if (isAxiosError(err)) {
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        setMiniSession(null);
      }
    }
    return Promise.reject(err);
  }
);

export async function authenticateWithInitData(initData: string): Promise<WebAppAuthResponse> {
  const { data } = await miniApi.post<WebAppAuthResponse>("/tg/webapp/auth", { initData });
  return data;
}
