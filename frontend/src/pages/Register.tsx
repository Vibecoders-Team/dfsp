import {useEffect, useRef, useState} from "react";
import {
    createBackupBlob,
    restoreFromBackup,
    getEOA,
    ensureEOA,
    ensureRSA,
    LOGIN_DOMAIN,
    LOGIN_TYPES,
    signLoginTyped,
    type LoginMessage,
} from "../lib/keychain";
import {ethers} from "ethers";
import {postChallenge, postRegister, ACCESS_TOKEN_KEY} from "../lib/api";

/** аккуратно достаём сообщение об ошибке без any */
function getErrorMessage(e: unknown, fallback: string): string {
    if (typeof e === "object" && e !== null) {
        const anyE = e as { message?: unknown; response?: { data?: { detail?: unknown } } };
        if (typeof anyE?.response?.data?.detail === "string") return anyE.response.data.detail;
        if (typeof anyE?.message === "string") return anyE.message;
    }
    return fallback;
}

/** assert-хелперы — линтер счастлив, TS получает сужение типов */
function assert(condition: unknown, message: string): asserts condition {
    if (!condition) throw new Error(message);
}

function assertHexAddress(a: string): asserts a is `0x${string}` {
    assert(/^0x[0-9a-fA-F]{40}$/.test(a), `Invalid hex address: ${a}`);
}

export default function RegisterPage() {
    const [address, setAddress] = useState<`0x${string}` | "">("");
    const [pubPem, setPubPem] = useState("");
    const [status, setStatus] = useState("");
    const [pwd, setPwd] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        (async () => {
            const w = await getEOA();
            if (w) setAddress(w.address as `0x${string}`);
        })();
    }, []);

    async function genKeys() {
        try {
            setStatus("Generating keys…");
            const w = await ensureEOA();
            const rsa = await ensureRSA();
            // убеждаемся в корректности адреса и даём TS узкий тип
            const addrStr = w.address;
            assertHexAddress(addrStr);
            setAddress(addrStr);
            setPubPem(rsa.publicPem);
            setStatus("Keys ready.");
        } catch (e: unknown) {
            setStatus(getErrorMessage(e, "Key generation error"));
        }
    }

    async function doRegister() {
        try {
            setStatus("Challenge…");
            const chal = await postChallenge();

            const eoa = await ensureEOA();
            const addrStr = eoa.address;
            assertHexAddress(addrStr);
            const addr = addrStr; // теперь addr: `0x${string}`
            const rsa = await ensureRSA();

            const message: LoginMessage = {address: addr, nonce: chal.nonce as `0x${string}`};

            setStatus("Signing…");
            const signature = await signLoginTyped(message);

            const recovered = ethers.verifyTypedData(LOGIN_DOMAIN, LOGIN_TYPES, message, signature);
            assert(
                recovered.toLowerCase() === addr.toLowerCase(),
                `local verify failed: recovered ${recovered} ≠ ${addr}`
            );

            const payload = {
                challenge_id: chal.challenge_id,
                eth_address: addr,
                rsa_public: rsa.publicPem,
                display_name: addr.slice(0, 10),
                typed_data: {domain: LOGIN_DOMAIN, types: LOGIN_TYPES, primaryType: "LoginChallenge", message},
                signature,
            };

            setStatus("Register…");
            const tok = await postRegister(payload);
            localStorage.setItem(ACCESS_TOKEN_KEY, tok.access);
            localStorage.setItem("REFRESH_TOKEN", tok.refresh);
            setStatus("Done.");
        } catch (e: unknown) {
            console.error(e);
            setStatus(getErrorMessage(e, "Register error"));
        }
    }

    async function backup() {
        try {
            if (!pwd) return setStatus("Enter password for backup");
            const blob = await createBackupBlob(pwd);
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = ".dfspkey";
            a.click();
            setStatus("Backup saved.");
        } catch (e: unknown) {
            setStatus(getErrorMessage(e, "Backup failed"));
        }
    }

    async function restore() {
        try {
            const f = fileRef.current?.files?.[0];
            if (!f) return setStatus("Pick .dfspkey file");
            if (!pwd) return setStatus("Enter password");
            const {address} = await restoreFromBackup(f, pwd);
            setAddress(address as `0x${string}`);
            setStatus("Restored.");
        } catch (e: unknown) {
            setStatus(getErrorMessage(e, "Restore failed"));
        }
    }

    function conMtmsk() { /* noop for now */
    }

    return (
        <div style={{maxWidth: 700, margin: "2rem auto", fontFamily: "Inter, system-ui"}}>
            <h2>Register (local keys)</h2>
            <p>Address: {address || "—"}</p>
            <div style={{display: "flex", gap: 8, flexWrap: "wrap"}}>
                <button onClick={genKeys}>Generate Keys</button>
                <button onClick={doRegister} disabled={!address}>Register</button>
            </div>

            <h3 style={{marginTop: 24}}>Backup / Restore</h3>
            <div style={{display: "grid", gap: 8, gridTemplateColumns: "1fr 1fr", alignItems: "center"}}>
                <input
                    type="password"
                    placeholder="backup password"
                    value={pwd}
                    onChange={(e) => setPwd(e.target.value)}
                />
                <div style={{display: "flex", gap: 8}}>
                    <button onClick={backup}>Backup .dfspkey</button>
                    <label style={{display: "inline-block"}}>
                        <input ref={fileRef} type="file" accept=".dfspkey,application/json" style={{display: "none"}}/>
                        <span style={{
                            padding: "6px 10px",
                            border: "1px solid #ccc",
                            cursor: "pointer"
                        }}>Pick .dfspkey</span>
                    </label>
                    <button onClick={restore}>Restore</button>
                </div>
            </div>

            {pubPem && (
                <>
                    <h3>RSA Public (PEM)</h3>
                    <pre style={{maxHeight: 240, overflow: "auto"}}>{pubPem}</pre>
                </>
            )}
            <p>{status}</p>
            <div style={{display: "flex", gap: 8}}>
                <button onClick={conMtmsk}>Connect with Metamask</button>
            </div>
        </div>
    );
}
