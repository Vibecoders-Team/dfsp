import { useMiniAuth } from "../auth";
import { useEffect, useState } from "react";
import { miniGet, MiniApiError } from "../api";
import { signNavigationPayload, type SignedPayload } from "../hmac";
import { openWebAppLink } from "../telegram";

type HealthSnapshot = { ok: boolean } | null;
type NavPreview = SignedPayload<{ route: string }> | null;

export function MiniHomePage() {
  const { session, method } = useMiniAuth();
  const [health, setHealth] = useState<HealthSnapshot>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [navSig, setNavSig] = useState<NavPreview>(null);

  useEffect(() => {
    if (!session) return;
    const probe = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await miniGet<{ ok: boolean }>("/health");
        setHealth({ ok: data.ok });
      } catch (err) {
        const msg = err instanceof MiniApiError ? err.message : "Ошибка проверки /health";
        setError(msg);
      } finally {
        setLoading(false);
      }
    };
    void probe();
  }, [session]);

  useEffect(() => {
    const buildNavSig = async () => {
      try {
        const signed = await signNavigationPayload({ route: "/mini/files" });
        setNavSig(signed);
      } catch (err) {
        console.warn("Failed to sign navigation payload", err);
      }
    };
    void buildNavSig();
  }, []);

  const cardStyle = {
    background: "var(--mini-bg-card)",
    border: "1px solid var(--mini-border)",
    borderRadius: "var(--mini-radius-lg)",
    padding: "16px",
    boxShadow: "var(--mini-shadow-sm)"
  };

  const features = [
    {
      icon: "📁",
      title: "Файлы",
      desc: "Управляйте файлами, шифрование и хранение в IPFS",
      gradient: "linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%)"
    },
    {
      icon: "🔐",
      title: "Доступы",
      desc: "Гранты и расшаривание с блокчейн-верификацией",
      gradient: "linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%)"
    },
    {
      icon: "✓",
      title: "Проверка",
      desc: "Сверка CID и метаданных on/off-chain",
      gradient: "linear-gradient(135deg, #10b981 0%, #34d399 100%)"
    },
    {
      icon: "🛡️",
      title: "Безопасность",
      desc: "HMAC подпись и JWT авторизация",
      gradient: "linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)"
    }
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Welcome Card */}
      <div style={{
        ...cardStyle,
        background: "var(--mini-gradient-primary)",
        color: "#fff",
        position: "relative",
        overflow: "hidden"
      }} className="mini-animate-slide-up">
        <div style={{
          position: "absolute",
          top: "-20px",
          right: "-20px",
          width: "100px",
          height: "100px",
          background: "rgba(255,255,255,0.1)",
          borderRadius: "50%"
        }} />
        <div style={{
          position: "absolute",
          bottom: "-30px",
          right: "40px",
          width: "60px",
          height: "60px",
          background: "rgba(255,255,255,0.05)",
          borderRadius: "50%"
        }} />
        <div style={{ position: "relative", zIndex: 1 }}>
          <p style={{
            fontSize: "20px",
            fontWeight: 600,
            marginBottom: "8px",
            display: "flex",
            alignItems: "center",
            gap: "8px"
          }}>
            👋 Добро пожаловать!
          </p>
          <p style={{
            fontSize: "14px",
            opacity: 0.9,
            lineHeight: 1.5,
            marginBottom: "12px"
          }}>
            Это мини-приложение DFSP для Telegram. Безопасное хранение файлов с блокчейн-верификацией.
          </p>
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 12px",
            background: "rgba(255,255,255,0.2)",
            borderRadius: "var(--mini-radius-full)",
            fontSize: "12px"
          }}>
            <span style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: method ? "#4ade80" : "#fbbf24"
            }} />
            Вход: {method === "telegram" ? "Telegram" : method === "ton" ? "TON Connect" : "Ожидание"}
          </div>
        </div>
      </div>

      {/* Status Card */}
      <div style={cardStyle} className="mini-animate-slide-up">
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "12px"
        }}>
          <p style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--mini-text)",
            margin: 0
          }}>
            Состояние системы
          </p>
          {loading && (
            <div style={{
              width: "16px",
              height: "16px",
              border: "2px solid var(--mini-border)",
              borderTopColor: "var(--mini-primary)",
              borderRadius: "50%"
            }} className="mini-animate-spin" />
          )}
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: "12px"
        }}>
          <div style={{
            padding: "12px",
            background: "var(--mini-bg-tertiary)",
            borderRadius: "var(--mini-radius)",
            textAlign: "center"
          }}>
            <p style={{
              fontSize: "11px",
              color: "var(--mini-text-muted)",
              marginBottom: "4px",
              textTransform: "uppercase",
              letterSpacing: "0.5px"
            }}>
              Сессия
            </p>
            <p style={{
              fontSize: "13px",
              fontWeight: 500,
              color: session ? "var(--mini-success)" : "var(--mini-text-muted)",
              fontFamily: "monospace"
            }}>
              {session ? `${session.slice(0, 8)}…` : "—"}
            </p>
          </div>
          <div style={{
            padding: "12px",
            background: "var(--mini-bg-tertiary)",
            borderRadius: "var(--mini-radius)",
            textAlign: "center"
          }}>
            <p style={{
              fontSize: "11px",
              color: "var(--mini-text-muted)",
              marginBottom: "4px",
              textTransform: "uppercase",
              letterSpacing: "0.5px"
            }}>
              Health
            </p>
            <p style={{
              fontSize: "13px",
              fontWeight: 500,
              color: health?.ok ? "var(--mini-success)" : error ? "var(--mini-danger)" : "var(--mini-text-muted)"
            }}>
              {loading ? "..." : health?.ok ? "✓ OK" : error ? "✗ Ошибка" : "—"}
            </p>
          </div>
        </div>

        {error && (
          <div style={{
            marginTop: "12px",
            padding: "10px 12px",
            background: "var(--mini-danger-light)",
            borderRadius: "var(--mini-radius)",
            fontSize: "12px",
            color: "var(--mini-danger-text)"
          }}>
            {error}
          </div>
        )}
      </div>

      {/* TON Warning */}
      {method === "ton" && (
        <div style={{
          ...cardStyle,
          background: "var(--mini-warning-light)",
          borderColor: "var(--mini-warning)"
        }} className="mini-animate-slide-up">
          <div style={{ display: "flex", alignItems: "flex-start", gap: "12px" }}>
            <span style={{ fontSize: "20px" }}>⚠️</span>
            <div>
              <p style={{
                fontSize: "14px",
                fontWeight: 600,
                color: "var(--mini-warning-text)",
                marginBottom: "4px"
              }}>
                Вход через TON Connect
              </p>
              <p style={{
                fontSize: "13px",
                color: "var(--mini-warning-text)",
                opacity: 0.8,
                marginBottom: "12px"
              }}>
                Для EVM-подписи перейдите на основной веб и свяжите EVM-адрес.
              </p>
              <button
                onClick={() => openWebAppLink("/files")}
                style={{
                  padding: "8px 16px",
                  borderRadius: "var(--mini-radius)",
                  border: "1px solid var(--mini-warning)",
                  background: "transparent",
                  color: "var(--mini-warning-text)",
                  fontSize: "13px",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "var(--mini-transition)"
                }}
              >
                Открыть веб-версию →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Features Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: "12px"
      }}>
        {features.map((feature, idx) => (
          <div
            key={feature.title}
            style={{
              ...cardStyle,
              cursor: "pointer",
              transition: "var(--mini-transition)"
            }}
            className="mini-animate-slide-up"
          >
            <div style={{
              width: "36px",
              height: "36px",
              borderRadius: "var(--mini-radius)",
              background: feature.gradient,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: "10px",
              fontSize: "18px"
            }}>
              {feature.icon}
            </div>
            <p style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--mini-text)",
              marginBottom: "4px"
            }}>
              {feature.title}
            </p>
            <p style={{
              fontSize: "12px",
              color: "var(--mini-text-muted)",
              lineHeight: 1.4
            }}>
              {feature.desc}
            </p>
          </div>
        ))}
      </div>

      {/* HMAC Preview */}
      {navSig && (
        <div style={cardStyle} className="mini-animate-slide-up">
          <p style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--mini-text)",
            marginBottom: "12px",
            display: "flex",
            alignItems: "center",
            gap: "8px"
          }}>
            🔏 Подпись навигации
          </p>
          <div style={{
            background: "var(--mini-bg-tertiary)",
            borderRadius: "var(--mini-radius)",
            padding: "12px",
            fontFamily: "monospace",
            fontSize: "11px"
          }}>
            <div style={{ marginBottom: "8px" }}>
              <span style={{ color: "var(--mini-text-muted)" }}>route: </span>
              <span style={{ color: "var(--mini-primary)" }}>{navSig.payload.route}</span>
            </div>
            <div style={{ marginBottom: "8px" }}>
              <span style={{ color: "var(--mini-text-muted)" }}>hmac: </span>
              <span style={{
                color: "var(--mini-success)",
                wordBreak: "break-all"
              }}>
                {navSig.hmac.slice(0, 32)}…
              </span>
            </div>
            <div>
              <span style={{ color: "var(--mini-text-muted)" }}>ts: </span>
              <span style={{ color: "var(--mini-text-secondary)" }}>{navSig.ts}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
