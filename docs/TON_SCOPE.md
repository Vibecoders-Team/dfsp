# TON-only account limitations

- TON login issues JWT tied to TON pubkey; a pseudo EVM address is derived for storage but **no EVM transactions** are performed for TON-only users.
- Actions requiring on-chain EVM signatures or contract calls (share/revoke/useOnce) are unavailable until the user links an EVM wallet.
- File ownership and grants recorded in DFSP remain off-chain for TON-only users; linking an EVM address will be required for any blockchain publishing.
- One user ↔ one TON pubkey; re-linking requires support intervention.
