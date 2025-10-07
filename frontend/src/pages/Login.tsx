import { useEffect, useState } from "react";
import { getEOA, LOGIN_DOMAIN, LOGIN_TYPES, signLoginTyped } from "../lib/keychain";
import { postChallenge, postLogin } from "../lib/api";

export default function LoginPage() {
  const [address, setAddress] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    (async () => {
      const w = await getEOA();
      if (w) setAddress(w.address);
    })();
  }, []);

  async function doLogin() {
    try {
      if (!address) return setStatus("No local DFSP EOA key. Generate/restore on Register page.");
      setStatus("Challenge…");
      const chal = await postChallenge();
      const message = { address, nonce: chal.nonce as `0x${string}` };

      setStatus("Signing…");
      const signature = await signLoginTyped(message);

      const payload = {
        challenge_id: chal.challenge_id,
        eth_address: address,
        typed_data: { domain: LOGIN_DOMAIN, types: LOGIN_TYPES, primaryType: "LoginChallenge", message },
        signature,
      };
      setStatus("Login…");
      const tok = await postLogin(payload);
      localStorage.setItem("ACCESS_TOKEN", tok.access);
      localStorage.setItem("REFRESH_TOKEN", tok.refresh);
      setStatus("Done.");
    } catch (e: any) {
      console.error(e);
      setStatus(e?.response?.data?.detail || e?.message || "Login error");
    }
  }

  return (
    <div style={{ maxWidth: 520, margin: "2rem auto", fontFamily: "Inter, system-ui" }}>
      <h2>Login (local EOA)</h2>
      <p>Address: {address || "—"}</p>
      <button onClick={doLogin} disabled={!address}>Login</button>
      <p>{status}</p>
    </div>
  );
}
