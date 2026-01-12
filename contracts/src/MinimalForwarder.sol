// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {MinimalForwarder as OZMinimalForwarder} from "@openzeppelin/contracts/metatx/MinimalForwarder.sol";

/// @dev Local name "MinimalForwarder" so hardhat generates the artifact
contract MinimalForwarder is OZMinimalForwarder {}
