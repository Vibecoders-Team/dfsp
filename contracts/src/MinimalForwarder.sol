// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {MinimalForwarder as OZMinimalForwarder} from "@openzeppelin/contracts/metatx/MinimalForwarder.sol";

/// @dev Локальное имя "MinimalForwarder", чтобы hardhat создавал артефакт
contract MinimalForwarder is OZMinimalForwarder {}
