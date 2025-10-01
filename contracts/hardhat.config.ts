import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.24",
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  paths: {
    sources: "src",      // <<< ВАЖНО: наши .sol лежат в ./src
    tests: "test",
    cache: "cache",
    artifacts: "artifacts",
  },
  networks: {
    localhost: { url: "http://127.0.0.1:8545" },
  },
  mocha: { timeout: 60_000 },
};

export default config;
