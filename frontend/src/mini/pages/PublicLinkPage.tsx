import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  miniGetPublicMeta,
  miniGetPublicContent,
  miniRequestPowChallenge,
  miniSubmitPow,
  normalizeMiniError,
  type MiniPublicMetaResp,
} from "../api";
import { decryptStream } from "@/lib/cryptoClient";

export function MiniPublicLinkPage() {
  const { token = "" } = useParams();
  const [meta, setMeta] = useState<MiniPublicMetaResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [powProgress, setPowProgress] = useState<string>("");

  const keyFromHash = (() => {
    try {
      const h = window.location.hash || "";
      const m = h.match(/[#&]k=([^&]+)/);
      if (!m) return null;
      const keyB64 = decodeURIComponent(m[1]);
      const raw = atob(keyB64);
      const key = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) key[i] = raw.charCodeAt(i);
      return key;
    } catch {
      return null;
    }
  })();

  useEffect(() => {
    if (!token) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const m = await miniGetPublicMeta(token);
        setMeta(m);
      } catch (err) {
        setError(normalizeMiniError(err).message);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [token]);

  const handleDownload = async () => {
    if (!meta) return;
    setDownloading(true);
    setError(null);
    setPowProgress("");

    try {
      // PoW if required
      const policy = meta.policy as Record<string, unknown> | undefined;
      const needPow = !!(policy && typeof policy === 'object' && Number(policy['pow_difficulty'] ?? 0) > 0);
      if (needPow) {
        setPowProgress("Requesting PoW challenge…");
        const ch = await miniRequestPowChallenge();
        const difficulty = Number(policy?.['pow_difficulty'] ?? ch.difficulty ?? 1) || 1;
        const nibbles = Math.floor((difficulty + 3) / 4);
        const prefix = "0".repeat(nibbles);
        let solution = "";
        let i = 0;
        const enc = new TextEncoder();
        while (true) {
          if (i % 1000 === 0) setPowProgress(`Solving PoW… tried ${i}`);
          const data = enc.encode(ch.challenge + i.toString(36));
          const digest = await crypto.subtle.digest("SHA-256", data);
          const hex = Array.from(new Uint8Array(digest))
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("");
          if (hex.startsWith(prefix)) {
            solution = i.toString(36);
            break;
          }
          i++;
          if (i > 5_000_000) throw new Error("PoW solve timeout");
        }
        setPowProgress("Submitting PoW solution…");
        await miniSubmitPow(token, ch.challenge, solution);
        setPowProgress("");
        await new Promise((res) => setTimeout(res, 100));
      }

      // Download with retry
      let blob: Blob | null = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          blob = await miniGetPublicContent(token);
          break;
        } catch (err: unknown) {
          const msg = normalizeMiniError(err).message;
          if (msg.includes("denied") && attempt < 2) {
            await new Promise((res) => setTimeout(res, 150));
            continue;
          }
          throw err;
        }
      }
      if (!blob) throw new Error("download_failed");

      // Decrypt if key present
      let finalBlob = blob;
      let finalName = (meta.name || "encrypted.bin").replace(/\s+/g, "_");
      if (keyFromHash) {
        try {
          const fakeResp = new Response(blob);
          finalBlob = await decryptStream(fakeResp, keyFromHash);
          if (finalName.endsWith(".enc")) {
            finalName = finalName.slice(0, -4);
          }
        } catch (e: unknown) {
          const msg = typeof e === 'object' && e && 'message' in e ? String((e as Record<string, unknown>).message ?? '') : '';
          setError("Decryption failed: " + (msg || 'unknown error'));
          setDownloading(false);
          return;
        }
      }

      // Trigger download
      const a = document.createElement("a");
      a.href = URL.createObjectURL(finalBlob);
      a.download = finalName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    } catch (err: unknown) {
      setError(normalizeMiniError(err).message);
    } finally {
      setDownloading(false);
      setPowProgress("");
    }
  };

  const cardStyle = {
    background: "var(--mini-bg-card)",
    border: "1px solid var(--mini-border)",
    borderRadius: "var(--mini-radius-lg)",
    padding: "16px",
    boxShadow: "var(--mini-shadow-sm)"
  };

  const formatFileSize = (bytes: number): string => {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const idx = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    const val = bytes / 1024 ** idx;
    return `${val.toFixed(val >= 10 ? 0 : 1)} ${units[idx]}`;
  };

  if (loading) {
    return (
      <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        <div style={{ height: "28px", borderRadius: "var(--mini-radius)" }} className="mini-skeleton" />
        <div style={{ height: "20px", borderRadius: "var(--mini-radius)", width: "60%" }} className="mini-skeleton" />
        <div style={{ height: "100px", borderRadius: "var(--mini-radius-lg)" }} className="mini-skeleton" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "16px" }}>
        <div style={{
          ...cardStyle,
          background: "var(--mini-danger-light)",
          borderColor: "var(--mini-danger)",
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
            margin: "0 auto 12px",
            fontSize: "24px",
            color: "#fff"
          }}>
            ✗
          </div>
          <p style={{
            fontSize: "14px",
            color: "var(--mini-danger-text)"
          }}>
            {error}
          </p>
        </div>
      </div>
    );
  }

  if (!meta) return null;

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
            📄 Публичный файл
          </p>
          <p style={{
            fontSize: "14px",
            opacity: 0.9
          }}>
            Скачайте файл по публичной ссылке
          </p>
        </div>
      </div>

      {/* File Details */}
      <div style={cardStyle} className="mini-animate-slide-up">
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: "12px",
          marginBottom: "0"
        }}>
          {[
            { label: "Имя", value: meta.name || "Без имени" },
            { label: "Размер", value: meta.size ? formatFileSize(meta.size) : "-" },
            { label: "Тип", value: meta.mime || "-" },
            { label: "Истекает", value: meta.expires_at ? new Date(meta.expires_at).toLocaleDateString() : "∞" }
          ].map((item) => (
            <div key={item.label} style={{
              padding: "12px",
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
                fontWeight: 500,
                wordBreak: "break-all"
              }}>
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Warning if no key */}
      {!keyFromHash && (
        <div style={{
          ...cardStyle,
          background: "var(--mini-warning-light)",
          borderColor: "var(--mini-warning)"
        }} className="mini-animate-slide-up">
          <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
            <span style={{ fontSize: "18px" }}>⚠️</span>
            <p style={{
              fontSize: "13px",
              color: "var(--mini-warning-text)"
            }}>
              Ключ расшифровки не найден в URL. Файл будет скачан в зашифрованном виде.
            </p>
          </div>
        </div>
      )}

      {/* Download Button */}
      <button
        onClick={handleDownload}
        disabled={downloading}
        style={{
          width: "100%",
          padding: "16px",
          borderRadius: "var(--mini-radius-lg)",
          border: "none",
          background: downloading ? "var(--mini-bg-tertiary)" : "var(--mini-primary)",
          color: downloading ? "var(--mini-text-muted)" : "#fff",
          fontSize: "16px",
          fontWeight: 600,
          cursor: downloading ? "not-allowed" : "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "10px",
          boxShadow: downloading ? "none" : "var(--mini-shadow)",
          transition: "var(--mini-transition)"
        }}
        className="mini-animate-slide-up"
      >
        {downloading ? (
          <>
            <div style={{
              width: "18px",
              height: "18px",
              border: "2px solid var(--mini-border)",
              borderTopColor: "var(--mini-text)",
              borderRadius: "50%"
            }} className="mini-animate-spin" />
            Скачивание...
          </>
        ) : (
          <>⬇️ Скачать файл</>
        )}
      </button>

      {/* PoW Progress */}
      {powProgress && (
        <div style={{
          textAlign: "center",
          padding: "12px",
          background: "var(--mini-bg-tertiary)",
          borderRadius: "var(--mini-radius)",
          fontSize: "13px",
          color: "var(--mini-text-secondary)"
        }} className="mini-animate-pulse">
          🔐 {powProgress}
        </div>
      )}
    </div>
  );
}
