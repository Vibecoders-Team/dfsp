import {useState} from "react";
import {ensureEOA, LOGIN_DOMAIN, LOGIN_TYPES, signLoginTyped} from "../lib/keychain";
import {postChallenge, postLogin, ACCESS_TOKEN_KEY} from "../lib/api";
import {
    ethers,
    type TypedDataDomain,
    type TypedDataField,
} from "ethers";

type LoginMessage = {
    address: `0x${string}`;
    nonce: `0x${string}`;
};

type EthersTypes = Record<string, TypedDataField[]>;
type ReadonlyEthersTypes = Readonly<Record<string, readonly TypedDataField[]>>;

function toEthersTypes(src: ReadonlyEthersTypes): EthersTypes {
    return Object.fromEntries(
        Object.entries(src)
            .filter(([k]) => k !== "EIP712Domain")
            .map(([k, arr]) => [k, Array.from(arr)])
    ) as EthersTypes;
}

function assert(condition: unknown, message: string): asserts condition {
    if (!condition) throw new Error(message);
}

function getErrorMessage(e: unknown, fallback: string): string {
    if (typeof e === "object" && e !== null) {
        const anyE = e as { message?: unknown; response?: { data?: { detail?: unknown } } };
        if (typeof anyE?.response?.data?.detail === "string") return anyE.response.data.detail;
        if (typeof anyE?.message === "string") return anyE.message;
    }
    return fallback;
}

export default function LoginPage() {
    const [status, setStatus] = useState("");
    const [addr, setAddr] = useState("");

    async function doLogin() {
        try {
            setStatus("Challenge…");
            const chal = await postChallenge();

            const eoa = await ensureEOA();
            const address = eoa.address as `0x${string}`;
            setAddr(address);

            const message: LoginMessage = {address, nonce: chal.nonce as `0x${string}`};

            // Готовим types под ethers v6
            const TYPES = toEthersTypes(LOGIN_TYPES as ReadonlyEthersTypes);

            setStatus("Signing…");
            const signature = await signLoginTyped(message);

            const recovered = ethers.verifyTypedData(
                LOGIN_DOMAIN as TypedDataDomain,
                TYPES,
                message,
                signature
            );
            assert(
                recovered.toLowerCase() === address.toLowerCase(),
                `local verify failed: recovered ${recovered} ≠ ${address}`
            );

            const payload = {
                challenge_id: chal.challenge_id,
                eth_address: address,
                typed_data: {
                    domain: LOGIN_DOMAIN,
                    types: TYPES, // уже без EIP712Domain, массивы — не readonly
                    primaryType: "LoginChallenge",
                    message,
                },
                signature,
            };

            setStatus("Login…");
            const tok = await postLogin(payload);
            localStorage.setItem(ACCESS_TOKEN_KEY, tok.access);
            localStorage.setItem("REFRESH_TOKEN", tok.refresh);

            setStatus("Done.");
        } catch (e: unknown) {
            console.error(e);
            setStatus(getErrorMessage(e, "Login error"));
        }
    }

    return (
        <div style={{maxWidth: 600, margin: "2rem auto", fontFamily: "Inter, system-ui"}}>
            <h2>Login</h2>
            <p>Address: {addr || "—"}</p>
            <button onClick={doLogin}>Login</button>
            <p>{status}</p>
        </div>
    );
}
