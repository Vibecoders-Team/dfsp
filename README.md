# Decentralized File Sharing Platform (DFSP)

Secure, gasless, user-friendly file sharing on top of IPFS + EVM smart contracts.
Files are encrypted client-side, stored by content hash (CID) on IPFS, while authenticity and access rights are recorded on-chain.
No wallets in the UI: users sign actions with an invisible key (ERC-2771), and a relayer submits transactions.

## Key Features

* Client-side encryption (AES-GCM) and per-recipient key delivery (RSA-OAEP).
* Content-addressed storage (IPFS): verify integrity via CID + on-chain checksum.
* Flexible sharing: individuals, saved recipient lists, and/or ephemeral public links with TTL & download limits.
* Revocation & versioning: revoke access instantly; publish new versions with preserved history.
* Gasless UX: ERC-2771 minimal forwarder + relayer; no wallets, no fees for users.
* Auditability without bloat: hourly Merkle anchoring of off-chain event logs to the chain.
* Polished web app: RU/EN, dark mode, PWA; 1-VPS deployment.

