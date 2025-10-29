import {ethers} from "ethers";

/**
 * Predict capId = keccak256(abi.encode(grantor, grantee, fileId, nonce+offset)).
 * - grantor, grantee: 0x-address strings (case-insensitive)
 * - fileId: 0x-hex32 or 32-byte Uint8Array
 * - nonce: bigint | number
 * - offset: bigint | number (default 0)
 */
export function predictCapId(
  grantor: string,
  grantee: string,
  fileId: `0x${string}` | Uint8Array,
  nonce: bigint | number,
  offset: bigint | number = 0
): `0x${string}` {
  const a = ethers.AbiCoder.defaultAbiCoder();
  const fidHex: `0x${string}` =
    typeof fileId === "string"
      ? (fileId as `0x${string}`)
      : (ethers.hexlify(fileId) as `0x${string}`);
  if (fidHex.length !== 66) throw new Error("fileId must be 0x-hex32");
  const n = BigInt(nonce) + BigInt(offset);
  const encoded = a.encode(["address", "address", "bytes32", "uint256"], [grantor, grantee, fidHex, n]);
  return ethers.keccak256(encoded) as `0x${string}`;
}

