// Унифицированный текст ошибки для UI
import { isAxiosError } from "axios";

export function getErrorMessage(e: unknown, fallback = "Request failed"): string {
  if (isAxiosError(e)) {
    const detail = (e.response?.data as any)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (e.response?.status === 404) return "Не найдено";
    if (e.response?.status === 401) return "Не авторизовано";
    if (e.response?.status === 403) return "Доступ запрещён";
    if (e.message) return e.message;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
