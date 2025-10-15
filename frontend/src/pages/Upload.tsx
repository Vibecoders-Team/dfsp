import {useState} from "react";
import {storeFile, fetchMeta, fetchVersions, fetchHistory} from "../lib/api";

/** минимальный тип того, что нам нужно от ответа upload */
type UploadOut = { id_hex: `0x${string}`; url?: string } & Record<string, unknown>;

function hasUrl(v: unknown): v is { url: string } {
    return typeof v === "object" && v !== null && typeof (v as Record<string, unknown>).url === "string";
}

function isUploadOut(v: unknown): v is UploadOut {
    return (
        typeof v === "object" &&
        v !== null &&
        typeof (v as Record<string, unknown>).id_hex === "string"
    );
}

function getErrorMessage(e: unknown, fallback: string): string {
    if (typeof e === "object" && e !== null) {
        const anyE = e as { message?: unknown; response?: { data?: { detail?: unknown } } };
        if (typeof anyE?.response?.data?.detail === "string") return anyE.response.data.detail;
        if (typeof anyE?.message === "string") return anyE.message;
    }
    return fallback;
}

export default function Upload() {
    const [file, setFile] = useState<File | null>(null);
    const [idHex, setIdHex] = useState("");
    const [out, setOut] = useState<UploadOut | null>(null);
    const [meta, setMeta] = useState<unknown>(null);
    const [versions, setVersions] = useState<unknown>(null);
    const [history, setHistory] = useState<unknown>(null);
    const [err, setErr] = useState("");
    const [loading, setLoading] = useState(false);

    async function onUpload() {
        setErr("");

        if (!file) return setErr("Pick a file");
        if (idHex && !/^0x[0-9a-fA-F]{64}$/.test(idHex)) {
            return setErr("id_hex must be 0x + 64 hex chars");
        }

        try {
            setLoading(true);
            setOut(null);
            setMeta(null);
            setVersions(null);
            setHistory(null);

            const res = await storeFile(file, idHex || undefined);

            if (!isUploadOut(res)) {
                setErr("Unexpected upload response");
                setLoading(false); // если у тебя есть loading
                return;
            }

            setOut(res);

            const [m, v, h] = await Promise.all([
                fetchMeta(res.id_hex),
                fetchVersions(res.id_hex),
                fetchHistory(res.id_hex),
            ]);
            setMeta(m);
            setVersions(v);
            setHistory(h);
        } catch (e: unknown) {
            setErr(getErrorMessage(e, "Upload failed"));
        } finally {
            setLoading(false);
        }
    }

    return (
        <div style={{maxWidth: 900, margin: "2rem auto", fontFamily: "Inter, system-ui"}}>
            <h2>Upload</h2>
            <div style={{display: "grid", gap: 8}}>
                <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)}/>
                <input
                    placeholder="optional id_hex (0x + 64)"
                    value={idHex}
                    onChange={(e) => setIdHex(e.target.value)}
                />
                <button onClick={onUpload} disabled={loading}>{loading ? "Storing…" : "Store"}</button>
            </div>

            {err && <p style={{color: "crimson"}}>{err}</p>}

            {out && (
                <>
                    <h3>Result</h3>
                    <pre>{JSON.stringify(out, null, 2)}</pre>
                    {hasUrl(out) && (
                        <a href={out.url} target="_blank" rel="noreferrer">
                            Open in IPFS
                        </a>
                    )}
                </>
            )}

            {meta !== null && (
                <>
                    <h3>Meta</h3>
                    <pre>{JSON.stringify(meta, null, 2)}</pre>
                </>
            )}

            {versions !== null && (
                <>
                    <h3>Versions</h3>
                    <pre>{JSON.stringify(versions, null, 2)}</pre>
                </>
            )}

            {history !== null && (
                <>
                    <h3>History</h3>
                    <pre>{JSON.stringify(history, null, 2)}</pre>
                </>
            )}
        </div>
    );
}
