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
      const needPow = !!(meta.policy && typeof meta.policy === "object" && (meta.policy as any).pow_difficulty > 0);
      if (needPow) {
        setPowProgress("Requesting PoW challenge…");
        const ch = await miniRequestPowChallenge();
        const difficulty = Number((meta.policy as any).pow_difficulty) || ch.difficulty || 1;
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
        } catch (err: any) {
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
        } catch (e: any) {
          setError("Decryption failed: " + (e?.message || "unknown error"));
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
    } catch (err) {
      setError(normalizeMiniError(err).message);
    } finally {
      setDownloading(false);
      setPowProgress("");
    }
  };

  if (loading) {
    return (
      <div className="p-4 space-y-2">
        <div className="h-6 bg-slate-700 rounded animate-pulse w-1/2" />
        <div className="h-4 bg-slate-700 rounded animate-pulse w-1/3" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-900/30 border border-red-500/50 text-red-100 rounded-lg p-3 text-sm">{error}</div>
      </div>
    );
  }

  if (!meta) return null;

  return (
    <div className="p-4 space-y-4">
      <section className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-2">
        <p className="text-lg font-semibold">Public File</p>
        <div className="space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-400">Name:</span>
            <span className="text-slate-100">{meta.name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Size:</span>
            <span className="text-slate-100">{meta.size ? `${meta.size} bytes` : "-"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">MIME:</span>
            <span className="text-slate-100">{meta.mime || "-"}</span>
          </div>
          {meta.expires_at && (
            <div className="flex justify-between">
              <span className="text-slate-400">Expires:</span>
              <span className="text-slate-100">{new Date(meta.expires_at).toLocaleString()}</span>
            </div>
          )}
        </div>
      </section>

      {!keyFromHash && (
        <div className="bg-amber-900/20 border border-amber-500/50 text-amber-50 rounded-lg p-3 text-xs">
          ⚠️ No decryption key found in URL. File will download encrypted.
        </div>
      )}

      <button
        onClick={handleDownload}
        disabled={downloading}
        className="w-full px-4 py-3 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium transition"
      >
        {downloading ? "Downloading…" : "Download"}
      </button>

      {powProgress && (
        <div className="text-xs text-slate-400 text-center">{powProgress}</div>
      )}
    </div>
  );
}

