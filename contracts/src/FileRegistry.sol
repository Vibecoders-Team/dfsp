// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/metatx/ERC2771Context.sol";

contract FileRegistry is ERC2771Context {
    struct FileMeta {
        address owner;
        string cid;
        bytes32 checksum;
        uint64 size;
        string mime;
        uint64 createdAt;
    }

    mapping(bytes32 => FileMeta) private _files;
    mapping(bytes32 => FileMeta[]) private _versions;

    event FileRegistered(bytes32 indexed fileId, address indexed owner, string cid, bytes32 checksum, uint64 size, string mime);
    event FileVersioned(bytes32 indexed fileId, string cid, bytes32 checksum, uint64 size, string mime);

    error AlreadyRegistered();
    error NotOwner();

    constructor(address trustedForwarder) ERC2771Context(trustedForwarder) {}

    function register(
        bytes32 fileId,
        string calldata cid,
        bytes32 checksum,
        uint64 size,
        string calldata mime
    ) external {
        if (_files[fileId].owner != address(0)) revert AlreadyRegistered();

        address sender = _msgSender();
        FileMeta memory m = FileMeta({
            owner: sender,
            cid: cid,
            checksum: checksum,
            size: size,
            mime: mime,
            createdAt: uint64(block.timestamp)
        });

        _files[fileId] = m;
        _versions[fileId].push(m);

        emit FileRegistered(fileId, sender, cid, checksum, size, mime);
    }

    function updateCid(
        bytes32 fileId,
        string calldata newCid,
        bytes32 newChecksum,
        uint64 newSize,
        string calldata newMime
    ) external {
        address sender = _msgSender();
        if (_files[fileId].owner != sender) revert NotOwner();

        _files[fileId].cid = newCid;
        _files[fileId].checksum = newChecksum;
        _files[fileId].size = newSize;
        _files[fileId].mime = newMime;

        FileMeta memory m = FileMeta({
            owner: sender,
            cid: newCid,
            checksum: newChecksum,
            size: newSize,
            mime: newMime,
            createdAt: uint64(block.timestamp)
        });
        _versions[fileId].push(m);

        emit FileVersioned(fileId, newCid, newChecksum, newSize, newMime);
    }

    function metaOf(bytes32 fileId) external view returns (FileMeta memory) {
        return _files[fileId];
    }

    function ownerOf(bytes32 fileId) external view returns (address) {
        return _files[fileId].owner;
    }

    function versionsOf(bytes32 fileId) external view returns (FileMeta[] memory) {
        return _versions[fileId];
    }

    // --- ERC-2771 glue ---
    function _msgSender() internal view override returns (address sender) {
        // единственный базовый — ERC2771Context
        return ERC2771Context._msgSender();
    }

    function _msgData() internal view override returns (bytes calldata) {
        return ERC2771Context._msgData();
    }
}
