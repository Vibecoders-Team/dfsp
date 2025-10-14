// src/pages/Login.tsx
import { useState } from "react";
import { ensureEOA, LOGIN_DOMAIN, LOGIN_TYPES, signLoginTyped } from "../lib/keychain";
import { postChallenge, postLogin } from "../lib/api";
import { ethers } from "ethers";

export default function LoginPage() {
  const [status, setStatus] = useState("");
  const [addr, setAddr] = useState("");

  async function doLogin() {
    try {
      setStatus("Challenge…");
      const chal = await postChallenge();

      const eoa = await ensureEOA();
      const address = eoa.address;
      setAddr(address);

      const message = { address, nonce: chal.nonce as `0x${string}` };

      setStatus("Signing…");
      const signature = await signLoginTyped(message);

      // локально проверим подпись
      const recovered = ethers.verifyTypedData(LOGIN_DOMAIN, LOGIN_TYPES, message, signature);
      if (recovered.toLowerCase() !== address.toLowerCase()) {
        throw new Error(`local verify failed: recovered ${recovered} ≠ ${address}`);
      }

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
    <div style={{ maxWidth: 600, margin: "2rem auto", fontFamily: "Inter, system-ui" }}>
      <h2>Login</h2>
      <p>Address: {addr || "—"}</p>
      <button onClick={doLogin}>Login</button>
      <p>{status}</p>
    </div>
  );
}
