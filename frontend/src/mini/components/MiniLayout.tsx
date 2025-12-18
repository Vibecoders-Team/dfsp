import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useMiniAuth } from "../auth";
import { useMiniTheme } from "../theme";
import { useState } from "react";
import "../styles/mini-theme.css";

const links = [
  { to: "/mini", label: "Главная", exact: true },
  { to: "/mini/files", label: "Файлы" },
  { to: "/mini/grants", label: "Доступы" },
  { to: "/mini/verify", label: "Проверка" },
];

export function MiniLayout({ children }: { children: ReactNode }) {
  const { status, error, expSeconds, method, tonAddress } = useMiniAuth();
  const { setTheme, theme } = useMiniTheme();
  const location = useLocation();
  const [showSettings, setShowSettings] = useState(false);

  const truncate = (value: string, len = 10) => {
    if (!value || value.length <= len) return value;
    const half = Math.floor(len / 2);
    return `${value.slice(0, half)}…${value.slice(-half)}`;
  };

  const getStatusColor = () => {
    switch (status) {
      case "ready": return "var(--mini-success)";
      case "error": return "var(--mini-danger)";
      case "authenticating": return "var(--mini-warning)";
      default: return "var(--mini-text-muted)";
    }
  };

  const getStatusText = () => {
    switch (status) {
      case "ready": return "Подключено";
      case "error": return "Ошибка";
      case "authenticating": return "Проверка...";
      default: return "Ожидание";
    }
  };

  return (
    <div className="mini-app" style={{
      display: "flex",
      flexDirection: "column",
      minHeight: "100vh",
      background: "var(--mini-bg)"
    }}>
      {/* Header */}
      <header style={{
        background: "var(--mini-bg-card)",
        borderBottom: "1px solid var(--mini-border)",
        padding: "12px 16px",
        position: "sticky",
        top: 0,
        zIndex: 40,
        boxShadow: "var(--mini-shadow-sm)"
      }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          maxWidth: "100%"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "40px",
              height: "40px",
              borderRadius: "var(--mini-radius-lg)",
              background: "var(--mini-gradient-primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--mini-shadow)"
            }}>
              <span style={{ fontSize: "18px", fontWeight: 700, color: "#fff" }}>D</span>
            </div>
            <div>
              <h1 style={{
                fontSize: "16px",
                fontWeight: 600,
                color: "var(--mini-text)",
                margin: 0,
                lineHeight: 1.3
              }}>
                DFSP
              </h1>
              <p style={{
                fontSize: "12px",
                color: "var(--mini-text-muted)",
                margin: 0,
                lineHeight: 1.3
              }}>
                Telegram Mini App
              </p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {/* Status indicator */}
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 10px",
              borderRadius: "var(--mini-radius-full)",
              background: "var(--mini-bg-tertiary)",
              fontSize: "12px"
            }}>
              <span style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: getStatusColor(),
                boxShadow: `0 0 6px ${getStatusColor()}`
              }} />
              <span style={{ color: "var(--mini-text-secondary)" }}>{getStatusText()}</span>
            </div>

            {/* Settings button */}
            <button
              onClick={() => setShowSettings(true)}
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "var(--mini-radius)",
                background: "var(--mini-bg-tertiary)",
                border: "none",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--mini-text-secondary)",
                transition: "var(--mini-transition)"
              }}
              className="mini-focus-ring"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav style={{
        background: "var(--mini-bg-card)",
        borderBottom: "1px solid var(--mini-border)",
        padding: "8px 12px",
        display: "flex",
        gap: "6px",
        overflowX: "auto",
        WebkitOverflowScrolling: "touch"
      }}>
        {links.map((link) => {
          const isActive = link.exact
            ? location.pathname === link.to
            : location.pathname.startsWith(link.to);

          return (
            <NavLink
              key={link.to}
              to={link.to}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                borderRadius: "var(--mini-radius-full)",
                fontSize: "13px",
                fontWeight: 500,
                textDecoration: "none",
                whiteSpace: "nowrap",
                transition: "var(--mini-transition)",
                background: isActive ? "var(--mini-primary)" : "var(--mini-bg-tertiary)",
                color: isActive ? "var(--mini-primary-text)" : "var(--mini-text-secondary)",
                boxShadow: isActive ? "var(--mini-shadow)" : "none"
              }}
            >
              {link.label}
            </NavLink>
          );
        })}
      </nav>

      {/* Main content */}
      <main style={{
        flex: 1,
        padding: "16px",
        maxWidth: "100%",
        overflow: "hidden"
      }} className="mini-animate-fade-in">
        {children}
      </main>

      {/* Settings Modal */}
      {showSettings && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "var(--mini-bg-modal)",
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            zIndex: 50,
            padding: "16px"
          }}
          onClick={(e) => e.target === e.currentTarget && setShowSettings(false)}
          className="mini-animate-fade-in"
        >
          <div
            style={{
              width: "100%",
              maxWidth: "400px",
              background: "var(--mini-bg-card)",
              borderRadius: "var(--mini-radius-xl)",
              boxShadow: "var(--mini-shadow-xl)",
              overflow: "hidden"
            }}
            className="mini-animate-slide-up"
          >
            {/* Modal Header */}
            <div style={{
              padding: "16px 20px",
              borderBottom: "1px solid var(--mini-border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between"
            }}>
              <h2 style={{
                fontSize: "18px",
                fontWeight: 600,
                color: "var(--mini-text)",
                margin: 0
              }}>
                Настройки
              </h2>
              <button
                onClick={() => setShowSettings(false)}
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "var(--mini-radius)",
                  background: "var(--mini-bg-tertiary)",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "18px",
                  color: "var(--mini-text-muted)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center"
                }}
              >
                ×
              </button>
            </div>

            {/* Modal Content */}
            <div style={{ padding: "16px 20px" }}>
              {/* Theme Toggle */}
              <div style={{
                background: "var(--mini-bg-tertiary)",
                borderRadius: "var(--mini-radius-lg)",
                padding: "16px",
                marginBottom: "16px"
              }}>
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "12px"
                }}>
                  <div>
                    <p style={{
                      fontSize: "14px",
                      fontWeight: 500,
                      color: "var(--mini-text)",
                      margin: 0
                    }}>
                      Тема оформления
                    </p>
                    <p style={{
                      fontSize: "12px",
                      color: "var(--mini-text-muted)",
                      margin: "4px 0 0 0"
                    }}>
                      {theme === "system" ? "Системная" : theme === "dark" ? "Тёмная" : "Светлая"}
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={theme === "light" ? "var(--mini-warning)" : "var(--mini-text-muted)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                    </svg>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={theme === "dark" ? "var(--mini-primary)" : "var(--mini-text-muted)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                    </svg>
                  </div>
                </div>

                {/* Theme Slider */}
                <div style={{
                  display: "flex",
                  gap: "4px",
                  background: "var(--mini-bg-card)",
                  borderRadius: "var(--mini-radius)",
                  padding: "4px"
                }}>
                  {(["light", "system", "dark"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setTheme(t)}
                      style={{
                        flex: 1,
                        padding: "8px 12px",
                        borderRadius: "var(--mini-radius-sm)",
                        border: "none",
                        cursor: "pointer",
                        fontSize: "13px",
                        fontWeight: 500,
                        transition: "var(--mini-transition)",
                        background: theme === t ? "var(--mini-primary)" : "transparent",
                        color: theme === t ? "var(--mini-primary-text)" : "var(--mini-text-secondary)"
                      }}
                    >
                      {t === "light" ? "Светлая" : t === "dark" ? "Тёмная" : "Авто"}
                    </button>
                  ))}
                </div>
              </div>

              {/* Account Info */}
              <div style={{
                background: "var(--mini-bg-tertiary)",
                borderRadius: "var(--mini-radius-lg)",
                padding: "16px"
              }}>
                <p style={{
                  fontSize: "14px",
                  fontWeight: 500,
                  color: "var(--mini-text)",
                  margin: "0 0 12px 0"
                }}>
                  Информация об аккаунте
                </p>

                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "13px"
                  }}>
                    <span style={{ color: "var(--mini-text-muted)" }}>Метод входа</span>
                    <span style={{
                      color: "var(--mini-text)",
                      background: "var(--mini-bg-card)",
                      padding: "4px 8px",
                      borderRadius: "var(--mini-radius-sm)",
                      fontWeight: 500
                    }}>
                      {method === "telegram" ? "Telegram" : method === "ton" ? "TON Connect" : "—"}
                    </span>
                  </div>

                  {tonAddress && (
                    <div style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "13px"
                    }}>
                      <span style={{ color: "var(--mini-text-muted)" }}>TON адрес</span>
                      <span style={{
                        color: "var(--mini-text)",
                        fontFamily: "monospace",
                        fontSize: "12px"
                      }}>
                        {truncate(tonAddress, 14)}
                      </span>
                    </div>
                  )}

                  {expSeconds !== null && (
                    <div style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "13px"
                    }}>
                      <span style={{ color: "var(--mini-text-muted)" }}>Сессия истекает</span>
                      <span style={{ color: "var(--mini-text)" }}>
                        {Math.floor(expSeconds / 60)} мин
                      </span>
                    </div>
                  )}

                  {error && (
                    <div style={{
                      marginTop: "8px",
                      padding: "8px 12px",
                      background: "var(--mini-danger-light)",
                      borderRadius: "var(--mini-radius)",
                      fontSize: "12px",
                      color: "var(--mini-danger-text)"
                    }}>
                      {error}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div style={{
              padding: "12px 20px 20px",
              display: "flex",
              gap: "8px"
            }}>
              <button
                onClick={() => setShowSettings(false)}
                style={{
                  flex: 1,
                  padding: "12px",
                  borderRadius: "var(--mini-radius)",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "14px",
                  fontWeight: 500,
                  background: "var(--mini-primary)",
                  color: "var(--mini-primary-text)",
                  transition: "var(--mini-transition)"
                }}
              >
                Готово
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
