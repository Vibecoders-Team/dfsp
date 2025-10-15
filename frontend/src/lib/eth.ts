import {ethers, type TypedDataDomain, type TypedDataField} from "ethers";

/** ---- EIP-712 ---- */
export const LOGIN_DOMAIN: TypedDataDomain = {name: "DFSP-Login", version: "1"};
export const LOGIN_TYPES: Record<string, TypedDataField[]> = {
    LoginChallenge: [
        {name: "address", type: "address"},
        {name: "nonce", type: "bytes32"},
    ],
};

export type LoginMessage = { address: `0x${string}`; nonce: `0x${string}` };

/** ---- EIP-1193 provider (без any) ---- */
type EIP1193Provider = {
    request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
};

function getInjectedProvider(): EIP1193Provider {
    const maybeEth = (window as unknown as { ethereum?: unknown }).ethereum;
    const req = (maybeEth as { request?: unknown })?.request;
    if (typeof req === "function") return maybeEth as EIP1193Provider;
    throw new Error("No wallet (window.ethereum not found)");
}

/** ---- Wallet connect / sign ---- */
export async function connectWallet(): Promise<{
    provider: ethers.BrowserProvider;
    address: `0x${string}`;
    chainId: number;
}> {
    const eth = getInjectedProvider();
    const provider = new ethers.BrowserProvider(eth);
    const [addressRaw] = (await provider.send("eth_requestAccounts", [])) as string[];
    const net = await provider.getNetwork();
    const address = addressRaw as `0x${string}`;
    return {provider, address, chainId: Number(net.chainId)};
}

export async function signLogin(provider: ethers.BrowserProvider, message: LoginMessage) {
    const signer = await provider.getSigner();
    const signature = await signer.signTypedData(LOGIN_DOMAIN, LOGIN_TYPES, message);
    return {signature};
}

/** ---- RSA PSS (SPKI PEM) ---- */
function ab2b64(ab: ArrayBuffer): string {
    const bytes = new Uint8Array(ab);
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
}

export async function generateRSA(): Promise<{ publicPem: string; privateKey: CryptoKey }> {
    const pair = await crypto.subtle.generateKey(
        {name: "RSA-PSS", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256"},
        true,
        ["sign", "verify"]
    );
    const spki = await crypto.subtle.exportKey("spki", pair.publicKey);
    const b64 = ab2b64(spki).match(/.{1,64}/g)!.join("\n");
    const pem = `-----BEGIN PUBLIC KEY-----\n${b64}\n-----END PUBLIC KEY-----\n`;
    return {publicPem: pem, privateKey: pair.privateKey};
}
