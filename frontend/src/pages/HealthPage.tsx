import {useEffect, useState} from "react";
import {fetchHealth} from "../lib/api";

function Badge({ok}: { ok: boolean }) {
    return (
        <span
            style={{
                display: "inline-block",
                padding: "2px 8px",
                borderRadius: 999,
                background: ok ? "rgba(0,180,0,.12)" : "rgba(200,0,0,.12)",
                border: `1px solid ${ok ? "rgba(0,180,0,.5)" : "rgba(200,0,0,.5)"}`,
                fontSize: 12,
            }}
        >
      {ok ? "OK" : "FAIL"}
    </span>
    );
}

/** ---- Типы ответа ---- */
type SubHealth = { ok: boolean; error?: string };
type Health = {
    ok: boolean;
    api?: SubHealth & { version?: string };
    db?: SubHealth;
    redis?: SubHealth;
    chain?: SubHealth & { chainId?: number | string };
    contracts?: SubHealth & { names?: string[] };
    ipfs?: SubHealth & { id?: string };
};
// Если у тебя у fetchHealth уже есть тип, можно так вместо интерфейсов:
// type Health = Awaited<ReturnType<typeof fetchHealth>>;

function getErrorMessage(e: unknown, fallback: string): string {
    if (typeof e === "object" && e !== null) {
        const anyE = e as { message?: unknown; response?: { data?: { detail?: unknown } } };
        if (typeof anyE?.response?.data?.detail === "string") return anyE.response.data.detail;
        if (typeof anyE?.message === "string") return anyE.message;
    }
    return fallback;
}

export default function HealthPage() {
    const [h, setH] = useState<Health | null>(null);
    const [err, setErr] = useState<string>("");
    const [loading, setLoading] = useState<boolean>(true);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setErr("");
        fetchHealth()
            .then((res) => {
                if (!cancelled) setH(res as Health); // убери "as Health", если fetchHealth типизирован
            })
            .catch((e: unknown) => {
                if (!cancelled) setErr(getErrorMessage(e, "error"));
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    return (
        <div style={{maxWidth: 900, margin: "2rem auto", fontFamily: "Inter, system-ui"}}>
            <h2>Health</h2>

            {loading && <p style={{opacity: 0.7}}>Loading…</p>}
            {err && <p style={{color: "crimson"}}>{err}</p>}

            {h && (
                <>
                    <div style={{marginBottom: 8}}>
                        Overall: <Badge ok={h.ok}/>
                    </div>

                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                            gap: 12,
                        }}
                    >
                        <div style={{border: "1px solid #eee", borderRadius: 8, padding: 12}}>
                            <div style={{display: "flex", justifyContent: "space-between"}}>
                                <b>API</b> <Badge ok={!!h.api?.ok}/>
                            </div>
                            <div style={{fontSize: 12, opacity: 0.8}}>
                                version: {h.api?.version ?? "dev"}
                            </div>
                            {h.api?.error && <pre style={{color: "crimson"}}>{h.api.error}</pre>}
                        </div>

                        <div style={{border: "1px solid #eee", borderRadius: 8, padding: 12}}>
                            <div style={{display: "flex", justifyContent: "space-between"}}>
                                <b>DB</b> <Badge ok={!!h.db?.ok}/>
                            </div>
                            {h.db?.error && <pre style={{color: "crimson"}}>{h.db.error}</pre>}
                        </div>

                        <div style={{border: "1px solid #eee", borderRadius: 8, padding: 12}}>
                            <div style={{display: "flex", justifyContent: "space-between"}}>
                                <b>Redis</b> <Badge ok={!!h.redis?.ok}/>
                            </div>
                            {h.redis?.error && <pre style={{color: "crimson"}}>{h.redis.error}</pre>}
                        </div>

                        <div style={{border: "1px solid #eee", borderRadius: 8, padding: 12}}>
                            <div style={{display: "flex", justifyContent: "space-between"}}>
                                <b>Chain</b> <Badge ok={!!h.chain?.ok}/>
                            </div>
                            <div style={{fontSize: 12, opacity: 0.8}}>
                                chainId: {h.chain?.chainId ?? "—"}
                            </div>
                            {h.chain?.error && <pre style={{color: "crimson"}}>{h.chain.error}</pre>}
                        </div>

                        <div style={{border: "1px solid #eee", borderRadius: 8, padding: 12}}>
                            <div style={{display: "flex", justifyContent: "space-between"}}>
                                <b>Contracts</b> <Badge ok={!!h.contracts?.ok}/>
                            </div>
                            <div style={{fontSize: 12, opacity: 0.8}}>
                                {Array.isArray(h.contracts?.names) ? h.contracts!.names!.join(", ") : "—"}
                            </div>
                            {h.contracts?.error && <pre style={{color: "crimson"}}>{h.contracts.error}</pre>}
                        </div>

                        <div style={{border: "1px solid #eee", borderRadius: 8, padding: 12}}>
                            <div style={{display: "flex", justifyContent: "space-between"}}>
                                <b>IPFS</b> <Badge ok={!!h.ipfs?.ok}/>
                            </div>
                            <div style={{fontSize: 12, opacity: 0.8}}>
                                id: {h.ipfs?.id ?? "—"}
                            </div>
                            {h.ipfs?.error && <pre style={{color: "crimson"}}>{h.ipfs.error}</pre>}
                        </div>
                    </div>

                    <h3 style={{marginTop: 16}}>Raw</h3>
                    <pre style={{fontSize: 12, opacity: 0.85}}>{JSON.stringify(h, null, 2)}</pre>
                </>
            )}
        </div>
    );
}
