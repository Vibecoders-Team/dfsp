import { ethers } from "ethers";

export const LOGIN_DOMAIN = { name: "DFSP-Login", version: "1" } as const;
export const LOGIN_TYPES = {
  LoginChallenge: [
    { name: "address", type: "address" },
    { name: "nonce",   type: "bytes32" },
  ],
} as const;

export type LoginMessage = { address: string; nonce: `0x${string}` };

export async function connectWallet(): Promise<{ provider: ethers.BrowserProvider; address: string; chainId: number }> {
  if (!(window as any).ethereum) throw new Error("No wallet");
  const provider = new ethers.BrowserProvider((window as any).ethereum);
  const [address] = await provider.send("eth_requestAccounts", []);
  const net = await provider.getNetwork();
  return { provider, address, chainId: Number(net.chainId) };
}

export async function signLogin(provider: ethers.BrowserProvider, message: LoginMessage) {
  const signer = await provider.getSigner();
  // ethers v6: signTypedData(domain, types, value)
  const signature = await (signer as any).signTypedData?.(LOGIN_DOMAIN, LOGIN_TYPES, message)
    ?? await signer.signMessage(JSON.stringify({ domain: LOGIN_DOMAIN, types: LOGIN_TYPES, message })); // fallback
  return { signature };
}

// --- RSA PSS (SPKI PEM) ---

function ab2b64(ab: ArrayBuffer): string {
  const bytes = new Uint8Array(ab);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

export async function generateRSA(): Promise<{ publicPem: string; privateKey: CryptoKey }> {
  const pair = await crypto.subtle.generateKey(
    { name: "RSA-PSS", modulusLength: 2048, publicExponent: new Uint8Array([0x01,0x00,0x01]), hash: "SHA-256" },
    true, ["sign","verify"]
  );
  const spki = await crypto.subtle.exportKey("spki", pair.publicKey);
  const b64 = ab2b64(spki).match(/.{1,64}/g)!.join("\n");
  const pem = `-----BEGIN PUBLIC KEY-----\n${b64}\n-----END PUBLIC KEY-----\n`;
  return { publicPem: pem, privateKey: pair.privateKey };
}
