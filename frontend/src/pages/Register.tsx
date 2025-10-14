import {useEffect, useRef, useState} from "react";
import {
    createBackupBlob,
    restoreFromBackup,
    getEOA
} from "../lib/keychain";
import {ethers} from "ethers";
import {ensureEOA, ensureRSA, LOGIN_DOMAIN, LOGIN_TYPES, signLoginTyped} from "../lib/keychain";
import {postChallenge, postRegister} from "../lib/api";


export default function RegisterPage() {
    const [address, setAddress] = useState("");
    const [pubPem, setPubPem] = useState("");
    const [status, setStatus] = useState("");
    const [pwd, setPwd] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        (async () => {
            const w = await getEOA();
            if (w) setAddress(w.address);
        })();
    }, []);

    async function genKeys() {
        try {
            setStatus("Generating keys…");
            const w = await ensureEOA();
            const rsa = await ensureRSA();
            setAddress(w.address);
            setPubPem(rsa.publicPem);
            setStatus("Keys ready.");
        } catch (e: any) {
            setStatus(e?.message || "Key generation error");
        }
    }

    async function doRegister() {
        try {
            setStatus("Challenge…");
            const chal = await postChallenge();

            // берём ОДИН wallet и адрес ТУТ
            const eoa = await ensureEOA();
            const addr = eoa.address;
            const rsa = await ensureRSA();

            const message = {address: addr, nonce: chal.nonce as `0x${string}`};

            setStatus("Signing…");
            const signature = await signLoginTyped(message); // должен подписывать ТЕМ ЖЕ eoa

            // локальная диагностика: проверить, что подпись действительно от addr
            const recovered = ethers.verifyTypedData(LOGIN_DOMAIN, LOGIN_TYPES, message, signature);
            if (recovered.toLowerCase() !== addr.toLowerCase()) {
                throw new Error(`local verify failed: recovered ${recovered} ≠ ${addr}`);
            }

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
            localStorage.setItem("ACCESS_TOKEN", tok.access);
            localStorage.setItem("REFRESH_TOKEN", tok.refresh);
            setStatus("Done.");
        } catch (e: any) {
            console.error(e);
            setStatus(e?.response?.data?.detail || e?.message || "Register error");
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
        } catch (e: any) {
            setStatus(e?.message || "Backup failed");
        }
    }

    async function restore() {
        try {
            const f = fileRef.current?.files?.[0];
            if (!f) return setStatus("Pick .dfspkey file");
            if (!pwd) return setStatus("Enter password");
            const {address} = await restoreFromBackup(f, pwd);
            setAddress(address);
            setStatus("Restored.");
        } catch (e: any) {
            setStatus(e?.message || "Restore failed");
        }
    }

    async function conMtmsk() {
        
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
                <input type="password" placeholder="backup password" value={pwd}
                       onChange={(e) => setPwd(e.target.value)}/>
                <div style={{display: "flex", gap: 8}}>
                    <button onClick={backup}>Backup .dfspkey</button>
                    <label style={{display: "inline-block"}}>
                        <input ref={fileRef} type="file" accept=".dfspkey,application/json" style={{display: "none"}}
                               onChange={() => {
                               }}/>
                        <span style={{
                            padding: "6px 10px",
                            border: "1px solid #ccc",
                            cursor: "pointer"
                        }}>Pick .dfspkey</span>
                    </label>
                    <button onClick={restore}>Restore</button>
                </div>
            </div>

            {pubPem && (<>
                <h3>RSA Public (PEM)</h3>
                <pre style={{maxHeight: 240, overflow: "auto"}}>{pubPem}</pre>
            </>)}
            <p>{status}</p>
            <div style={{display: "flex", gap: 8}}>
                <button onClick={conMtmsk}>Connect with Metamask</button>
            </div>
        </div>
    );
}
