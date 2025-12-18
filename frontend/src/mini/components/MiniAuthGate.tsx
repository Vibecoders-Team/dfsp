import type { ReactNode } from "react";
import { useMiniAuth } from "../auth";

export function MiniAuthGate({ children }: { children: ReactNode }) {
  const { status, error, reauthenticate, loginWithTon } = useMiniAuth();

  if (status === "authenticating" || status === "idle") {
    return (
      <div style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "60px 20px",
        textAlign: "center"
      }}>
        <div style={{
          width: "56px",
          height: "56px",
          borderRadius: "50%",
          border: "3px solid var(--mini-border)",
          borderTopColor: "var(--mini-primary)",
          marginBottom: "20px"
        }} className="mini-animate-spin" />
        <p style={{
          fontSize: "16px",
          fontWeight: 500,
          color: "var(--mini-text)",
          marginBottom: "8px"
        }}>
          Проверка авторизации
        </p>
        <p style={{
          fontSize: "14px",
          color: "var(--mini-text-muted)",
          marginBottom: "24px"
        }}>
          Валидируем initData из Telegram...
        </p>
        <button
          onClick={() => loginWithTon()}
          style={{
            padding: "10px 20px",
            borderRadius: "var(--mini-radius-full)",
            border: "1px solid var(--mini-border)",
            background: "var(--mini-bg-card)",
            color: "var(--mini-primary)",
            fontSize: "14px",
            fontWeight: 500,
            cursor: "pointer",
            transition: "var(--mini-transition)",
            display: "flex",
            alignItems: "center",
            gap: "8px"
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
          </svg>
          Войти через TON Connect
        </button>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div style={{
        maxWidth: "400px",
        margin: "0 auto"
      }}>
        <div style={{
          background: "var(--mini-bg-card)",
          border: "1px solid var(--mini-danger)",
          borderRadius: "var(--mini-radius-lg)",
          overflow: "hidden",
          boxShadow: "var(--mini-shadow)"
        }}>
          {/* Error Header */}
          <div style={{
            padding: "20px",
            background: "var(--mini-danger-light)",
            borderBottom: "1px solid var(--mini-danger)",
            textAlign: "center"
          }}>
            <div style={{
              width: "48px",
              height: "48px",
              borderRadius: "50%",
              background: "var(--mini-danger)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 12px"
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
            </div>
            <p style={{
              fontSize: "16px",
              fontWeight: 600,
              color: "var(--mini-danger-text)",
              margin: 0
            }}>
              Авторизация не прошла
            </p>
          </div>

          {/* Error Content */}
          <div style={{ padding: "20px" }}>
            <p style={{
              fontSize: "14px",
              color: "var(--mini-text-secondary)",
              marginBottom: "20px",
              lineHeight: 1.5
            }}>
              {error ?? "Неизвестная ошибка при проверке initData"}
            </p>

            <div style={{
              display: "flex",
              flexDirection: "column",
              gap: "10px"
            }}>
              <button
                onClick={() => reauthenticate()}
                style={{
                  width: "100%",
                  padding: "12px",
                  borderRadius: "var(--mini-radius)",
                  border: "none",
                  background: "var(--mini-primary)",
                  color: "var(--mini-primary-text)",
                  fontSize: "14px",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "var(--mini-transition)"
                }}
              >
                🔄 Повторить авторизацию
              </button>
              <button
                onClick={() => loginWithTon()}
                style={{
                  width: "100%",
                  padding: "12px",
                  borderRadius: "var(--mini-radius)",
                  border: "1px solid var(--mini-border)",
                  background: "var(--mini-bg-tertiary)",
                  color: "var(--mini-text)",
                  fontSize: "14px",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "var(--mini-transition)"
                }}
              >
                💎 Войти через TON Connect
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
