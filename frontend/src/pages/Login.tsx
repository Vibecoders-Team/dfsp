// src/pages/Login.tsx
import { useState } from "react";
import { connectWallet, signLogin, generateRSA, LOGIN_DOMAIN, LOGIN_TYPES } from "../lib/eth";
import { postChallenge, postLogin, postRegister } from "../lib/api";

export default function LoginPage() {
  const [address, setAddress] = useState<string>("");
  const [status, setStatus] = useState<string>("");

  async function auth(kind: "login"|"register") {
    try {
      setStatus("Connecting wallet…");
      const { provider, address: addr, chainId } = await connectWallet();
      setAddress(addr);

      setStatus("Challenge…");
      const chal = await postChallenge();
      const message = { address: addr, nonce: chal.nonce as `0x${string}` };

      setStatus("Signing EIP-712…");
      const { signature } = await signLogin(provider, message);

      const payload: any = {
        challenge_id: chal.challenge_id,
        eth_address: addr,
        typed_data: { domain: LOGIN_DOMAIN, types: LOGIN_TYPES, primaryType: "LoginChallenge", message },
        signature,
      };

      if (kind === "register") {
        setStatus("Generating RSA…");
        const { publicPem } = await generateRSA();
        payload.rsa_public = publicPem;
        payload.display_name = addr.slice(0, 10);
      }

      setStatus(kind === "register" ? "Register…" : "Login…");
      const tok = kind === "register" ? await postRegister(payload) : await postLogin(payload);
      localStorage.setItem("ACCESS_TOKEN", tok.access);
      localStorage.setItem("REFRESH_TOKEN", tok.refresh);
      setStatus("Done.");
    } catch (e: any) {
      console.error(e);
      setStatus(e?.response?.data?.detail || e?.message || "Error");
    }
  }

  return (
    <div className="container">
      <h2>DFSP Auth</h2>
      <p>Address: {address || "—"}</p>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={() => auth("register")}>Register</button>
        <button onClick={() => auth("login")}>Login</button>
      </div>
      <p>{status}</p>
    </div>
  );
}
