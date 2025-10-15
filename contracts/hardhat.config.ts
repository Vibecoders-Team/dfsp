import {HardhatUserConfig} from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";

dotenv.config();

const HARDHAT_URL = process.env.HARDHAT_URL || "http://127.0.0.1:8545";

const config: HardhatUserConfig = {
    solidity: {
        version: "0.8.24",
        settings: {optimizer: {enabled: true, runs: 200}},
    },
    paths: {
        sources: "src",
        tests: "test",
        cache: "cache",
        artifacts: "artifacts",
    },
    networks: {
        // локальная разработка на хосте
        localhost: {url: HARDHAT_URL},
        // запуск внутри docker-compose: обращаться к сервису chain
        docker: {url: "http://chain:8545"},
    },
    mocha: {timeout: 60_000},
};

export default config;
