import { useEffect, useMemo, useState } from "react";
import {
  miniCreateIntent,
  miniListFileGrants,
  miniListFiles,
  normalizeMiniError,
  type MiniFileListItem,
  type MiniGrantItem,
  miniCreatePublicLink,
  miniListPublicLinks,
  miniRevokePublicLink,
  type MiniPublicLinkItem,
  miniRenameFile,
} from "../api";
import { useMiniAuth } from "../auth";
import { openWebAppLink } from "../telegram";
import { getOrCreateFileKey } from "@/lib/fileKey";

type GrantsState = Record<string, { loading: boolean; error: string | null; items: MiniGrantItem[] }>;
type IntentPreview = {
  id: string;
  url: string;
  ttl: number;
  action: "share" | "revoke";
  targetId: string;
  createdAt: number;
};

const cardStyle = {
  background: "var(--mini-bg-card)",
  border: "1px solid var(--mini-border)",
  borderRadius: "var(--mini-radius-lg)",
  padding: "16px",
  boxShadow: "var(--mini-shadow-sm)"
};

export function MiniFilesPage() {
  const { session, method } = useMiniAuth();
  const [files, setFiles] = useState<MiniFileListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [grants, setGrants] = useState<GrantsState>({});
  const [intent, setIntent] = useState<IntentPreview | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Public links state
  const [publicLinks, setPublicLinks] = useState<MiniPublicLinkItem[]>([]);
  const [showPublicModal, setShowPublicModal] = useState(false);
  const [creatingPublic, setCreatingPublic] = useState(false);

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await miniListFiles();
        setFiles(data);
        setSelectedId((prev) => {
          if (prev) return prev;
          return data.length > 0 ? data[0].id : null;
        });
      } catch (err) {
        setError(resolveError(err));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [session]);

  useEffect(() => {
    if (!selectedId) return;
    void loadGrants(selectedId);
    void loadPublicLinks(selectedId);
  }, [selectedId]);

  const selectedFile = useMemo(() => files.find((f) => f.id === selectedId) || null, [files, selectedId]);
  const currentGrants = selectedId ? grants[selectedId] : undefined;
  const activeIntent = useMemo(() => {
    if (!intent) return null;
    if (intent.action === "share" && selectedFile && intent.targetId === selectedFile.id) return intent;
    if (intent.action === "revoke" && currentGrants?.items.some((g) => g.capId === intent.targetId)) return intent;
    return null;
  }, [intent, selectedFile, currentGrants]);

  const loadGrants = async (fileId: string) => {
    setGrants((prev) => ({
      ...prev,
      [fileId]: { loading: true, error: null, items: prev[fileId]?.items || [] },
    }));
    try {
      const items = await miniListFileGrants(fileId);
      setGrants((prev) => ({ ...prev, [fileId]: { loading: false, error: null, items } }));
    } catch (err) {
      setGrants((prev) => ({
        ...prev,
        [fileId]: { loading: false, error: resolveError(err), items: prev[fileId]?.items || [] },
      }));
    }
  };

  const loadPublicLinks = async (fileId: string) => {
    try {
      const items = await miniListPublicLinks(fileId);
      setPublicLinks(items);
    } catch {
      setPublicLinks([]);
    }
  };

  const handleCreatePublicLink = async () => {
    if (!selectedFile) return;
    setCreatingPublic(true);
    try {
      await miniCreatePublicLink(selectedFile.id, { max_downloads: 0 });
      await loadPublicLinks(selectedFile.id);
      setShowPublicModal(false);
    } catch (err) {
      setActionError(resolveError(err));
    } finally {
      setCreatingPublic(false);
    }
  };

  const handleRevokePublicLink = async (token: string) => {
    if (!selectedFile) return;
    try {
      await miniRevokePublicLink(token);
      await loadPublicLinks(selectedFile.id);
    } catch (err) {
      setActionError(resolveError(err));
    }
  };

  const handleStartRename = (file: MiniFileListItem) => {
    setRenamingId(file.id);
    setRenameValue(file.name || "");
    setRenameError(null);
  };

  const handleCancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
    setRenameError(null);
  };

  const handleSaveRename = async () => {
    if (!renamingId || !renameValue.trim()) {
      setRenameError("Name cannot be empty");
      return;
    }
    try {
      await miniRenameFile(renamingId, renameValue.trim());
      setFiles((prev) => prev.map((f) => (f.id === renamingId ? { ...f, name: renameValue.trim() } : f)));
      setRenamingId(null);
      setRenameValue("");
      setRenameError(null);
    } catch (err) {
      setRenameError(resolveError(err));
    }
  };

  const handleShareIntent = async () => {
    if (!selectedFile) return;
    setActionError(null);
    setActionLoading("share");
    try {
      const res = await miniCreateIntent("share", {
        fileId: selectedFile.id,
        fileName: selectedFile.name,
        source: "mini",
      });
      setIntent({
        id: res.intent_id,
        url: res.url,
        ttl: res.ttl,
        action: "share",
        targetId: selectedFile.id,
        createdAt: Date.now(),
      });
    } catch (err) {
      setActionError(resolveError(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevokeIntent = async (capId: string) => {
    const fid = selectedFile?.id || selectedId;
    if (!fid) return;
    setActionError(null);
    setActionLoading(`revoke:${capId}`);
    try {
      const res = await miniCreateIntent("revoke", {
        capId,
        fileId: fid,
        source: "mini",
      });
      setIntent({
        id: res.intent_id,
        url: res.url,
        ttl: res.ttl,
        action: "revoke",
        targetId: capId,
        createdAt: Date.now(),
      });
    } catch (err) {
      setActionError(resolveError(err));
    } finally {
      setActionLoading(null);
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
  };

  const formatBytes = (size: number) => {
    if (!size) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const idx = Math.min(units.length - 1, Math.floor(Math.log(size) / Math.log(1024)));
    const val = size / 1024 ** idx;
    return `${val.toFixed(val >= 10 ? 0 : 1)} ${units[idx]}`;
  };

  const truncate = (value: string, len = 10) => {
    if (!value || value.length <= len) return value;
    const half = Math.floor(len / 2);
    return `${value.slice(0, half)}…${value.slice(-half)}`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header Card */}
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
          width: "80px",
          height: "80px",
          background: "rgba(255,255,255,0.1)",
          borderRadius: "50%"
        }} />
        <div style={{ position: "relative", zIndex: 1 }}>
          <p style={{
            fontSize: "18px",
            fontWeight: 600,
            marginBottom: "8px",
            display: "flex",
            alignItems: "center",
            gap: "8px"
          }}>
            📁 Мои файлы
          </p>
          <p style={{
            fontSize: "14px",
            opacity: 0.9,
            lineHeight: 1.5
          }}>
            Шаринг и revoke через одноразовый intent с подписью на основном вебе
          </p>
        </div>
      </div>

      {error && (
        <div style={{
          ...cardStyle,
          background: "var(--mini-danger-light)",
          borderColor: "var(--mini-danger)",
          color: "var(--mini-danger-text)",
          fontSize: "14px"
        }}>
          {error}
        </div>
      )}

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
                Для EVM-подписи (grant/revoke) перейдите на веб и свяжите EVM-адрес.
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
                  cursor: "pointer"
                }}
              >
                Открыть веб-версию →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr",
        gap: "12px"
      }}>
        {/* Files List */}
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
              display: "flex",
              alignItems: "center",
              gap: "6px"
            }}>
              📂 Ваши файлы
              {files.length > 0 && (
                <span style={{
                  padding: "2px 8px",
                  borderRadius: "var(--mini-radius-full)",
                  background: "var(--mini-primary-light)",
                  color: "var(--mini-primary)",
                  fontSize: "12px",
                  fontWeight: 500
                }}>
                  {files.length}
                </span>
              )}
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

          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {[1, 2, 3].map((i) => (
                <div key={i} style={{ height: "56px" }} className="mini-skeleton" />
              ))}
            </div>
          ) : files.length === 0 ? (
            <div style={{
              textAlign: "center",
              padding: "32px 16px",
              color: "var(--mini-text-muted)"
            }}>
              <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }}>📭</span>
              <p style={{ fontSize: "14px" }}>Файлы не найдены</p>
            </div>
          ) : (
            <div style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              maxHeight: "300px",
              overflowY: "auto"
            }}>
              {files.map((f) => {
                const active = f.id === selectedId;
                const isRenaming = renamingId === f.id;
                return (
                  <div
                    key={f.id}
                    style={{
                      padding: "12px",
                      borderRadius: "var(--mini-radius)",
                      border: `1px solid ${active ? "var(--mini-primary)" : "var(--mini-border)"}`,
                      background: active ? "var(--mini-primary-light)" : "var(--mini-bg-tertiary)",
                      transition: "var(--mini-transition)",
                      cursor: isRenaming ? "default" : "pointer"
                    }}
                    onClick={() => !isRenaming && setSelectedId(f.id)}
                  >
                    {isRenaming ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        <input
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          style={{
                            padding: "8px 10px",
                            borderRadius: "var(--mini-radius-sm)",
                            border: "1px solid var(--mini-border)",
                            background: "var(--mini-bg-card)",
                            color: "var(--mini-text)",
                            fontSize: "13px"
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveRename();
                            if (e.key === "Escape") handleCancelRename();
                          }}
                          autoFocus
                          onClick={(e) => e.stopPropagation()}
                        />
                        {renameError && (
                          <p style={{ fontSize: "12px", color: "var(--mini-danger)" }}>{renameError}</p>
                        )}
                        <div style={{ display: "flex", gap: "6px" }}>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleSaveRename(); }}
                            style={{
                              padding: "6px 12px",
                              borderRadius: "var(--mini-radius-sm)",
                              border: "none",
                              background: "var(--mini-success)",
                              color: "#fff",
                              fontSize: "12px",
                              cursor: "pointer"
                            }}
                          >
                            Сохранить
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleCancelRename(); }}
                            style={{
                              padding: "6px 12px",
                              borderRadius: "var(--mini-radius-sm)",
                              border: "1px solid var(--mini-border)",
                              background: "var(--mini-bg-card)",
                              color: "var(--mini-text)",
                              fontSize: "12px",
                              cursor: "pointer"
                            }}
                          >
                            Отмена
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between"
                      }}>
                        <div>
                          <p style={{
                            fontSize: "14px",
                            fontWeight: 500,
                            color: active ? "var(--mini-primary)" : "var(--mini-text)",
                            marginBottom: "2px"
                          }}>
                            {f.name || "Без имени"}
                          </p>
                          <p style={{
                            fontSize: "12px",
                            color: "var(--mini-text-muted)",
                            fontFamily: "monospace"
                          }}>
                            {truncate(f.id, 14)} · {formatBytes(f.size)}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStartRename(f);
                          }}
                          style={{
                            width: "28px",
                            height: "28px",
                            borderRadius: "var(--mini-radius-sm)",
                            border: "none",
                            background: "var(--mini-bg-card)",
                            cursor: "pointer",
                            fontSize: "14px"
                          }}
                        >
                          ✏️
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected File Details */}
        {selectedFile && (
          <div style={cardStyle} className="mini-animate-slide-up">
            <p style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--mini-text)",
              marginBottom: "12px",
              display: "flex",
              alignItems: "center",
              gap: "6px"
            }}>
              📄 Детали файла
            </p>

            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: "10px",
              marginBottom: "16px"
            }}>
              {[
                { label: "Имя", value: selectedFile.name || "Без имени" },
                { label: "Размер", value: formatBytes(selectedFile.size) },
                { label: "CID", value: truncate(selectedFile.cid, 16), mono: true },
                { label: "Создан", value: formatDate(selectedFile.created_at) }
              ].map((item) => (
                <div key={item.label} style={{
                  padding: "10px",
                  background: "var(--mini-bg-tertiary)",
                  borderRadius: "var(--mini-radius)"
                }}>
                  <p style={{
                    fontSize: "11px",
                    color: "var(--mini-text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    marginBottom: "4px"
                  }}>
                    {item.label}
                  </p>
                  <p style={{
                    fontSize: "13px",
                    color: "var(--mini-text)",
                    fontFamily: item.mono ? "monospace" : "inherit",
                    wordBreak: "break-all"
                  }}>
                    {item.value}
                  </p>
                </div>
              ))}
            </div>

            <button
              onClick={handleShareIntent}
              disabled={actionLoading === "share"}
              style={{
                width: "100%",
                padding: "12px",
                borderRadius: "var(--mini-radius)",
                border: "none",
                background: actionLoading === "share" ? "var(--mini-bg-tertiary)" : "var(--mini-primary)",
                color: actionLoading === "share" ? "var(--mini-text-muted)" : "#fff",
                fontSize: "14px",
                fontWeight: 500,
                cursor: actionLoading === "share" ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px"
              }}
            >
              {actionLoading === "share" ? (
                <>
                  <div style={{
                    width: "14px",
                    height: "14px",
                    border: "2px solid var(--mini-border)",
                    borderTopColor: "var(--mini-text)",
                    borderRadius: "50%"
                  }} className="mini-animate-spin" />
                  Готовим intent...
                </>
              ) : (
                <>🔗 Создать intent для шаринга</>
              )}
            </button>

            {actionError && (
              <div style={{
                marginTop: "12px",
                padding: "10px",
                background: "var(--mini-danger-light)",
                borderRadius: "var(--mini-radius)",
                fontSize: "13px",
                color: "var(--mini-danger-text)"
              }}>
                {actionError}
              </div>
            )}

            {activeIntent && <IntentCallout intent={activeIntent} openLink={openWebAppLink} />}
          </div>
        )}

        {/* Public Links */}
        {selectedFile && (
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
                display: "flex",
                alignItems: "center",
                gap: "6px"
              }}>
                🔗 Публичные ссылки
              </p>
              <button
                onClick={() => setShowPublicModal(true)}
                style={{
                  padding: "6px 12px",
                  borderRadius: "var(--mini-radius-full)",
                  border: "none",
                  background: "var(--mini-primary)",
                  color: "#fff",
                  fontSize: "12px",
                  fontWeight: 500,
                  cursor: "pointer"
                }}
              >
                + Создать
              </button>
            </div>

            {publicLinks.length === 0 ? (
              <p style={{
                fontSize: "13px",
                color: "var(--mini-text-muted)",
                textAlign: "center",
                padding: "16px"
              }}>
                Нет публичных ссылок
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {publicLinks.map((pl) => (
                  <div key={pl.token} style={{
                    padding: "12px",
                    background: "var(--mini-bg-tertiary)",
                    borderRadius: "var(--mini-radius)"
                  }}>
                    <p style={{
                      fontSize: "12px",
                      color: "var(--mini-text-muted)",
                      fontFamily: "monospace",
                      marginBottom: "6px"
                    }}>
                      {truncate(pl.token, 20)}
                    </p>
                    <p style={{
                      fontSize: "12px",
                      color: "var(--mini-text-secondary)",
                      marginBottom: "8px"
                    }}>
                      Скачиваний: {pl.downloads_count ?? 0}
                      {pl.policy?.max_downloads && pl.policy.max_downloads > 0
                        ? ` / ${pl.policy.max_downloads}`
                        : " / ∞"}
                    </p>
                    <div style={{ display: "flex", gap: "6px" }}>
                      <button
                        onClick={() => {
                          if (!selectedFile) return;
                          const K_file = getOrCreateFileKey(selectedFile.id);
                          const keyB64 = btoa(String.fromCharCode(...K_file));
                          const origin = window.location.origin;
                          const url = `${origin}/mini/public/${pl.token}#k=${encodeURIComponent(keyB64)}`;
                          navigator.clipboard.writeText(url);
                        }}
                        style={{
                          padding: "6px 12px",
                          borderRadius: "var(--mini-radius-sm)",
                          border: "1px solid var(--mini-border)",
                          background: "var(--mini-bg-card)",
                          color: "var(--mini-text)",
                          fontSize: "12px",
                          cursor: "pointer"
                        }}
                      >
                        📋 Копировать
                      </button>
                      <button
                        onClick={() => handleRevokePublicLink(pl.token)}
                        style={{
                          padding: "6px 12px",
                          borderRadius: "var(--mini-radius-sm)",
                          border: "none",
                          background: "var(--mini-danger)",
                          color: "#fff",
                          fontSize: "12px",
                          cursor: "pointer"
                        }}
                      >
                        Отозвать
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Active Grants */}
        {selectedFile && currentGrants && (
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
                display: "flex",
                alignItems: "center",
                gap: "6px"
              }}>
                🔐 Активные гранты
              </p>
              {currentGrants.loading && (
                <div style={{
                  width: "14px",
                  height: "14px",
                  border: "2px solid var(--mini-border)",
                  borderTopColor: "var(--mini-primary)",
                  borderRadius: "50%"
                }} className="mini-animate-spin" />
              )}
            </div>

            {currentGrants.error && (
              <div style={{
                padding: "10px",
                background: "var(--mini-danger-light)",
                borderRadius: "var(--mini-radius)",
                fontSize: "13px",
                color: "var(--mini-danger-text)",
                marginBottom: "12px"
              }}>
                {currentGrants.error}
              </div>
            )}

            {currentGrants.items.length === 0 ? (
              <p style={{
                fontSize: "13px",
                color: "var(--mini-text-muted)",
                textAlign: "center",
                padding: "16px"
              }}>
                Грантов пока нет
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {currentGrants.items.map((g) => {
                  const busy = actionLoading === `revoke:${g.capId}`;
                  return (
                    <div key={g.capId} style={{
                      padding: "12px",
                      background: "var(--mini-bg-tertiary)",
                      borderRadius: "var(--mini-radius)"
                    }}>
                      <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "6px"
                      }}>
                        <span style={{
                          fontSize: "13px",
                          fontWeight: 500,
                          color: "var(--mini-text)"
                        }}>
                          {truncate(g.grantee, 14)}
                        </span>
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: "var(--mini-radius-full)",
                          background: g.status === "confirmed" ? "var(--mini-success-light)" : "var(--mini-bg-card)",
                          color: g.status === "confirmed" ? "var(--mini-success)" : "var(--mini-text-muted)",
                          fontSize: "11px",
                          fontWeight: 500,
                          textTransform: "uppercase"
                        }}>
                          {g.status}
                        </span>
                      </div>
                      <p style={{
                        fontSize: "11px",
                        color: "var(--mini-text-muted)",
                        fontFamily: "monospace",
                        marginBottom: "6px"
                      }}>
                        {truncate(g.capId, 24)}
                      </p>
                      <p style={{
                        fontSize: "12px",
                        color: "var(--mini-text-secondary)",
                        marginBottom: "10px"
                      }}>
                        DL {g.usedDownloads}/{g.maxDownloads} · до {formatDate(g.expiresAt)}
                      </p>
                      <button
                        onClick={() => handleRevokeIntent(g.capId)}
                        disabled={busy}
                        style={{
                          width: "100%",
                          padding: "8px",
                          borderRadius: "var(--mini-radius-sm)",
                          border: "none",
                          background: busy ? "var(--mini-bg-card)" : "var(--mini-danger)",
                          color: busy ? "var(--mini-text-muted)" : "#fff",
                          fontSize: "13px",
                          fontWeight: 500,
                          cursor: busy ? "not-allowed" : "pointer"
                        }}
                      >
                        {busy ? "Готовим intent..." : "❌ Отозвать"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Public Link Modal */}
      {showPublicModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "var(--mini-bg-modal)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 50,
            padding: "16px"
          }}
          onClick={(e) => e.target === e.currentTarget && setShowPublicModal(false)}
          className="mini-animate-fade-in"
        >
          <div
            style={{
              width: "100%",
              maxWidth: "340px",
              background: "var(--mini-bg-card)",
              borderRadius: "var(--mini-radius-lg)",
              boxShadow: "var(--mini-shadow-xl)",
              padding: "20px"
            }}
            className="mini-animate-scale-in"
          >
            <p style={{
              fontSize: "16px",
              fontWeight: 600,
              color: "var(--mini-text)",
              marginBottom: "8px"
            }}>
              Создать публичную ссылку
            </p>
            <p style={{
              fontSize: "13px",
              color: "var(--mini-text-secondary)",
              marginBottom: "16px"
            }}>
              Будет создана ссылка с безлимитными скачиваниями для файла «{selectedFile?.name || ""}»
            </p>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={handleCreatePublicLink}
                disabled={creatingPublic}
                style={{
                  flex: 1,
                  padding: "12px",
                  borderRadius: "var(--mini-radius)",
                  border: "none",
                  background: creatingPublic ? "var(--mini-bg-tertiary)" : "var(--mini-primary)",
                  color: creatingPublic ? "var(--mini-text-muted)" : "#fff",
                  fontSize: "14px",
                  fontWeight: 500,
                  cursor: creatingPublic ? "not-allowed" : "pointer"
                }}
              >
                {creatingPublic ? "Создаём..." : "Создать"}
              </button>
              <button
                onClick={() => setShowPublicModal(false)}
                style={{
                  padding: "12px 16px",
                  borderRadius: "var(--mini-radius)",
                  border: "1px solid var(--mini-border)",
                  background: "var(--mini-bg-tertiary)",
                  color: "var(--mini-text)",
                  fontSize: "14px",
                  cursor: "pointer"
                }}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function IntentCallout({ intent, openLink }: { intent: IntentPreview; openLink: (url: string) => void }) {
  const [remainingSec, setRemainingSec] = useState(() => calcRemaining(intent));

  useEffect(() => {
    const tick = () => setRemainingSec(calcRemaining(intent));
    const id = window.setInterval(tick, 1_000);
    tick();
    return () => clearInterval(id);
  }, [intent]);

  const expired = remainingSec <= 0;
  const minutes = Math.max(1, Math.ceil(remainingSec / 60));
  const expiresAt = new Date(intent.createdAt + intent.ttl * 1000);
  const expiresAtLabel = expiresAt.toLocaleTimeString("ru-RU", { timeStyle: "short" });
  const expiryLabel = expired
    ? "Intent истёк, создайте новый"
    : `≈${minutes} мин (до ${expiresAtLabel})`;

  return (
    <div style={{
      marginTop: "12px",
      padding: "14px",
      background: expired ? "var(--mini-danger-light)" : "var(--mini-primary-light)",
      borderRadius: "var(--mini-radius)",
      border: `1px solid ${expired ? "var(--mini-danger)" : "var(--mini-primary)"}`
    }} className="mini-animate-scale-in">
      <p style={{
        fontSize: "13px",
        fontWeight: 600,
        color: expired ? "var(--mini-danger-text)" : "var(--mini-primary)",
        marginBottom: "8px",
        display: "flex",
        alignItems: "center",
        gap: "6px"
      }}>
        {expired ? "⏰ Intent истёк" : "✓ Intent готов"}
      </p>
      <p style={{
        fontSize: "12px",
        color: "var(--mini-text-secondary)",
        marginBottom: "6px",
        fontFamily: "monospace",
        wordBreak: "break-all"
      }}>
        {intent.url}
      </p>
      <p style={{
        fontSize: "12px",
        color: "var(--mini-text-muted)",
        marginBottom: "12px"
      }}>
        {intent.action === "share" ? "Шаринг" : "Отзыв"} · {expiryLabel} · одноразовый
      </p>
      <div style={{ display: "flex", gap: "8px" }}>
        <button
          onClick={() => !expired && openLink(intent.url)}
          disabled={expired}
          style={{
            flex: 1,
            padding: "10px",
            borderRadius: "var(--mini-radius-sm)",
            border: "none",
            background: expired ? "var(--mini-bg-tertiary)" : "var(--mini-primary)",
            color: expired ? "var(--mini-text-muted)" : "#fff",
            fontSize: "13px",
            fontWeight: 500,
            cursor: expired ? "not-allowed" : "pointer"
          }}
        >
          Открыть
        </button>
        <button
          onClick={() => !expired && navigator.clipboard.writeText(intent.url)}
          disabled={expired}
          style={{
            padding: "10px 16px",
            borderRadius: "var(--mini-radius-sm)",
            border: "1px solid var(--mini-border)",
            background: "var(--mini-bg-card)",
            color: expired ? "var(--mini-text-muted)" : "var(--mini-text)",
            fontSize: "13px",
            cursor: expired ? "not-allowed" : "pointer"
          }}
        >
          📋
        </button>
      </div>
      {expired && (
        <p style={{
          marginTop: "10px",
          fontSize: "12px",
          color: "var(--mini-danger-text)"
        }}>
          Intent истёк — создайте новый (они одноразовые)
        </p>
      )}
    </div>
  );
}

function resolveError(err: unknown): string {
  const normalized = normalizeMiniError(err);
  if (normalized.status === 410 || normalized.code === "expired") return "Intent истёк, создайте новый.";
  if (normalized.status === 409 || normalized.code === "already_used") return "Intent уже использован (одноразовый).";
  return normalized.message || "Неизвестная ошибка";
}

function calcRemaining(intent: IntentPreview): number {
  const expiresAt = intent.createdAt + intent.ttl * 1000;
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
}
