import { useEffect, useMemo, useState } from "react";
import { miniListFiles, miniVerify, normalizeMiniError, type MiniFileListItem, type MiniVerifyResponse } from "../api";
import { openWebAppLink } from "../telegram";
import { useMiniAuth } from "../auth";
import { useSearchParams } from "react-router-dom";

type VerifyState = "idle" | "loading" | "ready" | "error";

const cardStyle = {
  background: "var(--mini-bg-card)",
  border: "1px solid var(--mini-border)",
  borderRadius: "var(--mini-radius-lg)",
  padding: "16px",
  boxShadow: "var(--mini-shadow-sm)"
};

export function MiniVerifyPage() {
  const { session } = useMiniAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialId = searchParams.get("fileId") || "";

  const [fileId, setFileId] = useState(initialId);
  const [files, setFiles] = useState<MiniFileListItem[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [verifyState, setVerifyState] = useState<VerifyState>("idle");
  const [result, setResult] = useState<MiniVerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    const load = async () => {
      setLoadingFiles(true);
      try {
        const list = await miniListFiles();
        setFiles(list);
        if (!fileId && list.length > 0) {
          setFileId(list[0].id);
          setSearchParams({ fileId: list[0].id });
        }
      } catch {
        /* keep silent; verify still works with manual input */
      } finally {
        setLoadingFiles(false);
      }
    };
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  const handleVerify = async () => {
    const trimmed = fileId.trim();
    if (!trimmed) {
      setError("Provide fileId (0x…) for verification.");
      return;
    }
    setSearchParams(trimmed ? { fileId: trimmed } : {});
    setVerifyState("loading");
    setError(null);
    try {
      const data = await miniVerify(trimmed);
      setResult(data);
      setVerifyState("ready");
    } catch (err) {
      setResult(null);
      setVerifyState("error");
      setError(resolveVerifyError(err));
    }
  };

  const match = result?.match === true;
  const offchain = result?.offchain;
  const onchain = result?.onchain;

  const selectedOptions = useMemo(() => files.slice(0, 6), [files]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header Card */}
      <div style={{
        ...cardStyle,
        background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
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
            ✓ File verification
          </p>
          <p style={{
            fontSize: "14px",
            opacity: 0.9,
            lineHeight: 1.5
          }}>
            Compare off-chain (DB) and on-chain metadata: CID, checksum, size, and MIME
          </p>
        </div>
      </div>

      {/* Search Card */}
      <div style={cardStyle} className="mini-animate-slide-up">
        <div style={{
          display: "flex",
          gap: "10px",
          marginBottom: "12px"
        }}>
          <input
            value={fileId}
            onChange={(e) => setFileId(e.target.value)}
            placeholder="0x… fileId"
            style={{
              flex: 1,
              padding: "12px 14px",
              borderRadius: "var(--mini-radius)",
              border: "1px solid var(--mini-border)",
              background: "var(--mini-bg-tertiary)",
              color: "var(--mini-text)",
              fontSize: "14px",
              outline: "none",
              transition: "var(--mini-transition)"
            }}
          />
          <button
            onClick={handleVerify}
            disabled={verifyState === "loading"}
            style={{
              padding: "12px 20px",
              borderRadius: "var(--mini-radius)",
              border: "none",
              background: verifyState === "loading" ? "var(--mini-bg-tertiary)" : "var(--mini-success)",
              color: verifyState === "loading" ? "var(--mini-text-muted)" : "#fff",
              fontSize: "14px",
              fontWeight: 500,
              cursor: verifyState === "loading" ? "not-allowed" : "pointer",
              transition: "var(--mini-transition)",
              display: "flex",
              alignItems: "center",
              gap: "6px"
            }}
          >
            {verifyState === "loading" ? (
              <>
                <div style={{
                  width: "14px",
                  height: "14px",
                  border: "2px solid var(--mini-border)",
                  borderTopColor: "var(--mini-text)",
                  borderRadius: "50%"
                }} className="mini-animate-spin" />
                <span>...</span>
              </>
            ) : (
              <>✓ Verify</>
            )}
          </button>
        </div>

        {loadingFiles ? (
          <p style={{
            fontSize: "12px",
            color: "var(--mini-text-muted)"
          }}>
            Loading your files...
          </p>
        ) : selectedOptions.length > 0 && (
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "6px"
          }}>
            <span style={{
              fontSize: "12px",
              color: "var(--mini-text-muted)",
              marginRight: "4px"
            }}>
              Quick pick:
            </span>
            {selectedOptions.map((f, idx) => (
              <button
                key={f.id}
                onClick={() => {
                  setFileId(f.id);
                  setSearchParams({ fileId: f.id });
                }}
                style={{
                  padding: "4px 10px",
                  borderRadius: "var(--mini-radius-full)",
                  border: "1px solid var(--mini-border)",
                  background: fileId === f.id ? "var(--mini-primary-light)" : "var(--mini-bg-tertiary)",
                  color: fileId === f.id ? "var(--mini-primary)" : "var(--mini-text-secondary)",
                  fontSize: "12px",
                  cursor: "pointer",
                  transition: "var(--mini-transition)"
                }}
              >
                {f.name || `File ${idx + 1}`}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div style={{
            marginTop: "12px",
            padding: "10px 12px",
            background: "var(--mini-danger-light)",
            borderRadius: "var(--mini-radius)",
            fontSize: "13px",
            color: "var(--mini-danger-text)"
          }}>
            {error}
          </div>
        )}
      </div>

      {verifyState === "ready" && result && (
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: "12px"
        }}>
          <StatusCard match={match} onchain={onchain ?? null} offchain={offchain ?? null} />
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: "12px"
          }}>
            <MetaCard title="On-chain" meta={onchain} />
            <MetaCard title="Off-chain" meta={offchain} />
          </div>
        </div>
      )}

      {verifyState === "error" && !result && (
        <div style={{
          ...cardStyle,
          background: "var(--mini-danger-light)",
          borderColor: "var(--mini-danger)"
        }}>
          <p style={{
            fontSize: "14px",
            color: "var(--mini-danger-text)"
          }}>
            {error || "Verification failed."}
          </p>
        </div>
      )}

      {result && (
        <div style={cardStyle} className="mini-animate-slide-up">
          <p style={{
            fontSize: "14px",
            color: "var(--mini-text-secondary)",
            marginBottom: "12px"
          }}>
            Detailed verification and local file upload are available on the main web app.
          </p>
          <button
            onClick={() => openWebAppLink(`/verify/${fileId}`)}
            style={{
              padding: "10px 20px",
              borderRadius: "var(--mini-radius)",
              border: "1px solid var(--mini-border)",
              background: "var(--mini-bg-tertiary)",
              color: "var(--mini-text)",
              fontSize: "14px",
              cursor: "pointer",
              transition: "var(--mini-transition)"
            }}
          >
            Open /verify/{truncate(fileId, 14)} on the web →
          </button>
        </div>
      )}
    </div>
  );
}

function StatusCard({
  match,
  onchain,
  offchain,
}: {
  match: boolean;
  onchain: MiniVerifyResponse["onchain"];
  offchain: MiniVerifyResponse["offchain"];
}) {
  const hint = (() => {
    if (!onchain && offchain) return "No on-chain record for this fileId.";
    if (!offchain && onchain) return "No off-chain data for this file.";
    if (!onchain && !offchain) return "No metadata available.";
    if (!match) return "Checksum does not match between on-chain and off-chain.";
    return "Checksum matches - file verified.";
  })();

  return (
    <div
      style={{
        ...cardStyle,
        background: match ? "var(--mini-success-light)" : "var(--mini-warning-light)",
        borderColor: match ? "var(--mini-success)" : "var(--mini-warning)",
        textAlign: "center",
        padding: "24px"
      }}
      className="mini-animate-scale-in"
    >
      <div style={{
        width: "56px",
        height: "56px",
        borderRadius: "50%",
        background: match ? "var(--mini-success)" : "var(--mini-warning)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        margin: "0 auto 12px",
        fontSize: "24px"
      }}>
        {match ? "✓" : "⚠"}
      </div>
      <p style={{
        fontSize: "11px",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        color: match ? "var(--mini-success-text)" : "var(--mini-warning-text)",
        marginBottom: "4px"
      }}>
        {match ? "match=true" : "match=false"}
      </p>
      <p style={{
        fontSize: "16px",
        fontWeight: 600,
        color: match ? "var(--mini-success-text)" : "var(--mini-warning-text)",
        marginBottom: "8px"
      }}>
        {match ? "Checksum matches" : "Different or missing"}
      </p>
      <p style={{
        fontSize: "13px",
        color: match ? "var(--mini-success-text)" : "var(--mini-warning-text)",
        opacity: 0.8
      }}>
        {hint}
      </p>
    </div>
  );
}

function MetaCard({ title, meta }: { title: string; meta: MiniVerifyResponse["onchain"] | null | undefined }) {
  return (
    <div style={{
      ...cardStyle,
      padding: "14px"
    }} className="mini-animate-slide-up">
      <p style={{
        fontSize: "13px",
        fontWeight: 600,
        color: "var(--mini-text)",
        marginBottom: "12px",
        display: "flex",
        alignItems: "center",
        gap: "6px"
      }}>
        {title === "On-chain" ? "⛓️" : "💾"} {title}
      </p>
      {meta ? (
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: "8px"
        }}>
          <Row label="CID" value={meta.cid || "-"} />
          <Row label="Checksum" value={truncate(meta.checksum || "-", 16)} monospace />
          <Row label="Size" value={formatBytes(meta.size)} />
          <Row label="MIME" value={meta.mime || "-"} />
          {meta.name && <Row label="Name" value={meta.name} />}
        </div>
      ) : (
        <p style={{
          fontSize: "13px",
          color: "var(--mini-text-muted)",
          fontStyle: "italic"
        }}>
          No data
        </p>
      )}
    </div>
  );
}

function Row({ label, value, monospace }: { label: string; value: string; monospace?: boolean }) {
  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "flex-start",
      gap: "8px"
    }}>
      <span style={{
        fontSize: "12px",
        color: "var(--mini-text-muted)",
        flexShrink: 0
      }}>
        {label}
      </span>
      <span style={{
        fontSize: "12px",
        color: "var(--mini-text)",
        textAlign: "right",
        wordBreak: "break-all",
        fontFamily: monospace ? "monospace" : "inherit"
      }}>
        {value}
      </span>
    </div>
  );
}

function formatBytes(size: number) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const idx = Math.min(units.length - 1, Math.floor(Math.log(size) / Math.log(1024)));
  const val = size / 1024 ** idx;
  return `${val.toFixed(val >= 10 ? 0 : 1)} ${units[idx]}`;
}

function truncate(value: string, len = 10) {
  if (!value || value.length <= len) return value;
  const half = Math.floor(len / 2);
  return `${value.slice(0, half)}…${value.slice(-half)}`;
}

function resolveVerifyError(err: unknown): string {
  const normalized = normalizeMiniError(err);
  if (normalized.status === 404 || normalized.code === "file_not_found") return "File not found.";
  if (normalized.status === 400 || normalized.code === "bad_file_id") return "Invalid fileId.";
  return normalized.message || "Verification error.";
}
