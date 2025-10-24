// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/metatx/ERC2771Context.sol";

contract AccessControlDFSP is ERC2771Context {
    struct Grant {
        address grantor;
        address grantee;
        bytes32 fileId;
        uint64 expiresAt;
        uint32 maxDownloads;
        uint32 used;
        uint64 createdAt;
        bool revoked;
    }

    mapping(bytes32 => Grant) public grants;
    mapping(address => bytes32[]) private _grantsOf;

    // ✅ стабильный источник энтропии для capId
    mapping(address => uint256) public grantNonces;

    event Granted(bytes32 indexed capId, address indexed grantor, address indexed grantee, bytes32 fileId, uint64 expiresAt, uint32 maxDownloads);
    event Revoked(bytes32 indexed capId, address indexed grantor);
    event Used(bytes32 indexed capId, uint32 used);

    error AlreadyExists();
    error NotGrantor();
    error NotGrantee();
    error RevokedGrant();
    error ExpiredGrant();
    error ExhaustedGrant();
    error MaxDownloadsZero();
    error BearerNotEnabled();
    error InvalidGrantee(); // New error for zero-address grantee

    constructor(address trustedForwarder) ERC2771Context(trustedForwarder) {}

    function grant(
        bytes32 fileId,
        address grantee,
        uint64 ttlSec,
        uint32 maxDownloads
    ) external returns (bytes32 capId) {
        if (maxDownloads == 0) revert MaxDownloadsZero();
        if (grantee == address(0)) revert InvalidGrantee(); // Check for zero address

        uint64 exp = uint64(block.timestamp) + ttlSec;

        // ✅ детерминированный capId: зависит только от состояния (нонса), а не от blockhash/времени
        uint256 n = grantNonces[_msgSender()];
        capId = keccak256(abi.encode(_msgSender(), grantee, fileId, n)); // n — текущий нонс грантора

        if (grants[capId].createdAt != 0) revert AlreadyExists();

        Grant memory g = Grant({
            grantor: _msgSender(),
            grantee: grantee,
            fileId: fileId,
            expiresAt: exp,
            maxDownloads: maxDownloads,
            used: 0,
            createdAt: uint64(block.timestamp),
            revoked: false
        });

        grants[capId] = g;
        _grantsOf[grantee].push(capId);

        // ✅ инкремент после фиксации capId
        unchecked {grantNonces[_msgSender()] = n + 1;}

        emit Granted(capId, g.grantor, g.grantee, g.fileId, g.expiresAt, g.maxDownloads);
    }

    function revoke(bytes32 capId) external {
        Grant storage g = grants[capId];
        if (g.grantor != _msgSender()) revert NotGrantor();
        if (g.revoked) revert RevokedGrant();
        g.revoked = true;
        emit Revoked(capId, g.grantor);
    }

    function useOnce(bytes32 capId) external {
        Grant storage g = grants[capId];
        if (g.grantee != _msgSender()) revert NotGrantee();
        if (g.revoked) revert RevokedGrant();
        if (block.timestamp > g.expiresAt) revert ExpiredGrant();
        if (g.used >= g.maxDownloads) revert ExhaustedGrant();
        unchecked {g.used += 1;}
        emit Used(capId, g.used);
    }

    function canDownload(address user, bytes32 fileId) external view returns (bool) {
        bytes32[] memory ids = _grantsOf[user];
        for (uint256 i = 0; i < ids.length; ++i) {
            Grant storage g = grants[ids[i]];
            if (
                g.fileId == fileId &&
                !g.revoked &&
                block.timestamp <= g.expiresAt &&
                g.used < g.maxDownloads
            ) {
                return true;
            }
        }
        return false;
    }

    function grantBearer(bytes32, uint64, uint32) external pure returns (bytes32) {
        revert BearerNotEnabled();
    }

    // --- ERC-2771 glue ---
    function _msgSender() internal view override returns (address sender) {
        return ERC2771Context._msgSender();
    }

    function _msgData() internal view override returns (bytes calldata) {
        return ERC2771Context._msgData();
    }
}
