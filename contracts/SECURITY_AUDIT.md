# DFSP Contracts — Sprint 3 Security Review (Task #72)

Date: 2025-11-01
Scope: contracts in `contracts/src/` — AccessControlDFSP.sol, FileRegistry.sol, DFSPAnchoring.sol, MinimalForwarder.sol (OZ)

Summary
- Outcome: No critical or high-severity issues identified in the current scope.
- Architecture uses ERC-2771 for meta-transactions in stateful contracts (AccessControlDFSP, FileRegistry) with consistent `_msgSender()` usage. Anchoring is `Ownable`-gated.
- Reentrancy risk: none observed (no external calls in state-changing functions). `nonReentrant` not required at present.
- Integer safety: Solidity ^0.8.24 checks over/underflow. A few `unchecked` increments are deliberately used with guards and bounded widths.
- Gas: Small structs use `uint64/uint32` where appropriate and pack well. No obvious storage bloat. Minor view loop in `canDownload()` is acceptable for off-chain reads.
- Events: State transitions emit events with key fields indexed within the 3-index limit.

Manual Review Checklist (AC mapping)
1) Reentrancy / CEI
- Checked functions that mutate state in AccessControlDFSP (`grant`, `revoke`, `useOnce`) and FileRegistry (`register`, `updateCid`). None perform external calls; only state writes and event emission. CEI pattern is effectively satisfied; `nonReentrant` not needed now.
- No `call`/`transfer`/`send` or external interface calls are present.

2) Access control
- ERC-2771-context contracts consistently use `_msgSender()` (not `msg.sender`) for authorization and attribution.
- FileRegistry: `updateCid` enforces `NotOwner()` for non-owners. `register` binds `owner` to `_msgSender()`.
- AccessControlDFSP: grantor-only `revoke`, grantee-only `useOnce` enforced via `_msgSender()`.
- DFSPAnchoring: `onlyOwner` for `anchorMerkleRoot` validated via OZ Ownable.

3) Integer overflow/underflow
- Solidity ^0.8 auto-checks are in effect.
- `grant`: `grantNonces[_msgSender()]` increment in `unchecked { n + 1; }` — safe; nonces are unbounded, but overflow is practically unreachable. Deterministic capId uses current nonce before increment.
- `useOnce`: `unchecked { g.used += 1; }` is gated by `g.used < g.maxDownloads` with both `uint32`; overflow is impossible given the guard and width.
- Expiry: `uint64(block.timestamp) + ttlSec` reverts on overflow; TTL is user-controlled but constrained by 64-bit range; using 64-bit is intentional for gas/storage.

4) Gas optimization
- Structs use `uint64/uint32` (AccessControlDFSP.Grant, FileRegistry.FileMeta). Layout packs small fields into a single slot (post-`bytes32`) — verified.
- No redundant storage reads of the same slot within a function. Local caching of `_msgSender()` applied in FileRegistry.
- No low-level loops in state-changing functions; `canDownload()` is a `view` helper intended for off-chain calls; linear scan is acceptable. Batch ops can be added later if product needs (see "Future improvements").
- No unnecessary `immutable` opportunities identified without forking OZ implementations. Trusted forwarder is stored by OZ base contract.

5) Event emission
- All state-changing functions emit events:
  - AccessControlDFSP: `Granted`, `Revoked`, `Used`.
  - FileRegistry: `FileRegistered`, `FileVersioned`.
  - DFSPAnchoring: `Anchored`.
- Indexing:
  - Granted: `capId`, `grantor`, `grantee` are indexed (three-parameter index cap reached). The `fileId` is included in the event payload for correlation.
  - Revoked: `capId`, `grantor` are indexed.
  - Used: `capId` is indexed.
  - File events: `fileId` and `owner` are indexed where relevant.

Static Analysis (how to run)
Note: Tooling is environment-dependent; run locally or in CI. Ensure Solidity compiler matches `hardhat.config.ts`.

- Slither (no critical issues expected)
  - Install: `pipx install slither-analyzer` (or `pip install slither-analyzer` in a venv)
  - Run (from `contracts/`):
    ```bash
    slither . --solc-remaps @openzeppelin=node_modules/@openzeppelin --filter-paths "node_modules|hardhat"
    ```
  - Expected: informational notes (timestamp usage, view loop). No critical/high findings.

- Mythril (optional)
  - Install: `pipx install mythril`
  - Run targeted checks:
    ```bash
    myth analyze src/AccessControlDFSP.sol --solc-json hardhat.compile.json || true
    myth analyze src/FileRegistry.sol --solc-json hardhat.compile.json || true
    myth analyze src/DFSPAnchoring.sol --solc-json hardhat.compile.json || true
    ```
  - Expected: no criticals. False positives are possible for meta-tx patterns.

Local Build & Tests
```bash
cd contracts
npm ci --no-audit --no-fund
npm run build
npm test
```

Findings & Notes
- Timestamp dependence: expiry uses `block.timestamp` — acceptable for TTL semantics (informational).
- Linear scan in `canDownload()`: `view` only; for large per-user grant sets consider a future indexed mapping `{fileId => capId}` or active set per user.
- Event indexing trade-off: `Granted` already uses 3 indexed topics (capId/grantor/grantee). Indexing `fileId` simultaneously is not possible without removing another index; current choice is reasonable for lookup by participant and capId.
- No external calls from state-changing functions — reentrancy risk is absent; adding `nonReentrant` would add overhead without benefit now.

Future Improvements (non-blocking)
- Batch grant helper for multiple recipients to reduce per-grant overhead (API can still pre-compute `capId`s deterministically).
- Optional `revokeBatch(bytes32[] capIds)` for admin UX.
- Dedicated mapping for quick `canDownload(fileId)` lookup if on-chain evaluation becomes frequent on-chain (currently intended for off-chain reads).

Appendix: File-by-File Quick Notes
- AccessControlDFSP.sol
  - Uses ERC-2771, `_msgSender()` everywhere.
  - `InvalidGrantee` check prevents zero-address grants.
  - Deterministic `capId` with `grantNonces[grantor]` — aligns with backend pre-compute.
- FileRegistry.sol
  - Ownership per `fileId`; `updateCid` gated by `_msgSender()`.
  - Metadata sizes are `uint64` (MVP-limits fit; off-chain enforces 200MB in API).
- DFSPAnchoring.sol
  - `onlyOwner` protected; emits `Anchored`. No state kept beyond events (MVP).
- MinimalForwarder.sol
  - OZ reference implementation is imported and wrapped.

AC Status
- CEI/Reentrancy: Done (no external calls; CEI effectively satisfied).
- Access control: Done (onlyOwner / _msgSender() verified where needed).
- Integer safety: Done (0.8 checks; `unchecked` justified and safe).
- Gas optimization: Done (packing reviewed; widths minimized; minor view loop acknowledged).
- Event emission + indexing: Done (key fields indexed within limits).
- Slither/Mythril: Ready-to-run instructions provided; expected no critical issues in current code.

