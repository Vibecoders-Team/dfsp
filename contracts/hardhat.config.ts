import type { HardhatUserConfig } from "hardhat/config";
import hardhatToolboxMochaEthers from "@nomicfoundation/hardhat-toolbox-mocha-ethers";
import * as dotenv from "dotenv";

dotenv.config();

const HARDHAT_URL = process.env.HARDHAT_URL || "http://127.0.0.1:8545";

const config: HardhatUserConfig = {
  plugins: [hardhatToolboxMochaEthers],

  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },

  paths: {
    sources: "src",
    tests: "test",
    cache: "cache",
    artifacts: "artifacts",
  },

  networks: {
    // локальный RPC-узел на хосте
    localhost: { type: "http", url: HARDHAT_URL },
    // контейнерный RPC по имени сервиса chain
    docker: { type: "http", url: "http://chain:8545" },
    // при желании можно добавить встроенную сеть:
    // hardhat: { type: "edr-simulated" },
  },

  // В HH3 конфиг для Mocha находится в test.mocha
  test: { mocha: { timeout: 60_000 } },
};

export default config;
