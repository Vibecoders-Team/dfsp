// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

contract DFSPAnchoring is Ownable {
    event Anchored(bytes32 indexed root, uint64 indexed periodId);

    constructor(address owner_) {
        _transferOwnership(owner_); // у OZ v4.x конструктор Ownable без аргументов
    }

    function anchorMerkleRoot(bytes32 root, uint64 periodId) external onlyOwner {
        emit Anchored(root, periodId);
    }
}
