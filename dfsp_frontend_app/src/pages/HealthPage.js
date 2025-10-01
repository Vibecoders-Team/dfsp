import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
export default function HealthPage() {
    const [s, setS] = useState({ status: "idle" });
    useEffect(() => {
        (async () => {
            setS({ status: "loading" });
            try {
                const api = import.meta.env.VITE_API_URL || "";
                const res = await fetch(`${api}/health`);
                if (!res.ok)
                    throw new Error(`HTTP ${res.status}`);
                const json = await res.json();
                setS({ status: "ok", data: json });
            }
            catch (e) {
                setS({ status: "error", data: { message: e.message } });
            }
        })();
    }, []);
    return (_jsxs("main", { children: [_jsx("h1", { children: "/health" }), _jsxs("p", { children: ["Status: ", s.status] }), _jsx("pre", { children: JSON.stringify(s.data ?? {}, null, 2) })] }));
}
