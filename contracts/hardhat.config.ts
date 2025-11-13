// hardhat.config.ts
import type { HardhatUserConfig } from "hardhat/config";
import * as dotenv from "dotenv";

// Use canonical toolbox (bundles ethers + chai matchers) for Hardhat v2
import "@nomicfoundation/hardhat-toolbox";
import "hardhat-gas-reporter";

dotenv.config();

const HARDHAT_URL = process.env.HARDHAT_URL || "http://127.0.0.1:8545";

const config: HardhatUserConfig = {
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
    localhost: { url: HARDHAT_URL },
    docker: { url: HARDHAT_URL },
  },
  mocha: {
    timeout: 60_000,
  },
  gasReporter: {
    enabled: true,
    outputFile: "gas-report.txt",
    noColors: true,
    currency: "USD",
    // coinmarketcap: process.env.COINMARKETCAP_API_KEY, // optional for price lookup
    // token: "ETH",
  },
};

export default config;
