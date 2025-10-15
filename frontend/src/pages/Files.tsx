import {useState} from "react";
import {fetchCid, fetchMeta, fetchVersions, fetchHistory} from "../lib/api";

// Узкий гард, чтобы безопасно читать cid.url
function hasUrl(v: unknown): v is { url: string } {
    return typeof v === "object"
        && v !== null
        && "url" in v
        && typeof (v as Record<string, unknown>).url === "string";
}

// Достаём вменяемое сообщение об ошибке без any
function getErrorMessage(e: unknown, fallback: string): string {
    if (typeof e === "object" && e !== null) {
        if ("response" in e) {
            const r = (e as { response?: unknown }).response;
            if (typeof r === "object" && r !== null && "data" in r) {
                const d = (r as { data?: unknown }).data;
                if (typeof d === "object" && d !== null && "detail" in d) {
                    const detail = (d as { detail?: unknown }).detail;
                    if (typeof detail === "string") return detail;
                }
            }
        }
        if ("message" in e && typeof (e as { message?: unknown }).message === "string") {
            return (e as { message: string }).message;
        }
    }
    return fallback;
}

export default function Files() {
    const [idHex, setIdHex] = useState("");
    const [cid, setCid] = useState<unknown>(null);
    const [meta, setMeta] = useState<unknown>(null);
    const [versions, setVersions] = useState<unknown>(null);
    const [history, setHistory] = useState<unknown>(null);
    const [err, setErr] = useState("");

    async function onResolve() {
        setErr("");
        setCid(null);
        try {
            const res = await fetchCid(idHex);
            setCid(res);
        } catch (e: unknown) {
            setErr(getErrorMessage(e, "Resolve failed"));
        }
    }

    async function onMeta() {
        setErr("");
        setMeta(null);
        try {
            const res = await fetchMeta(idHex);
            setMeta(res);
        } catch (e: unknown) {
            setErr(getErrorMessage(e, "Meta failed"));
        }
    }

    async function onVersions() {
        setErr("");
        setVersions(null);
        try {
            const res = await fetchVersions(idHex);
            setVersions(res);
        } catch (e: unknown) {
            setErr(getErrorMessage(e, "Versions failed"));
        }
    }

    async function onHistory() {
        setErr("");
        setHistory(null);
        try {
            const res = await fetchHistory(idHex);
            setHistory(res);
        } catch (e: unknown) {
            setErr(getErrorMessage(e, "History failed"));
        }
    }

    return (
        <div style={{maxWidth: 900, margin: "2rem auto", fontFamily: "Inter, system-ui"}}>
            <h2>Files</h2>
            <div style={{display: "grid", gap: 8, gridTemplateColumns: "1fr auto", alignItems: "center"}}>
                <input placeholder="id_hex (0x + 64)" value={idHex} onChange={(e) => setIdHex(e.target.value)}/>
                <div style={{display: "flex", gap: 8}}>
                    <button onClick={onResolve}>CID</button>
                    <button onClick={onMeta}>Meta</button>
                    <button onClick={onVersions}>Versions</button>
                    <button onClick={onHistory}>History</button>
                </div>
            </div>

            {err && <p style={{color: "crimson"}}>{err}</p>}

            {cid !== null && (
                <>
                    <h3>CID</h3>
                    <pre>{JSON.stringify(cid, null, 2)}</pre>
                    {hasUrl(cid) && (
                        <a href={cid.url} target="_blank" rel="noreferrer">
                            Open
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
