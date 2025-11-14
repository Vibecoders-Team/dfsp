#!/bin/sh
set -euo pipefail
DATADIR="/data"
GENESIS="/genesis/genesis.json"
CHAIN_ID="${CHAIN_ID:-31337}"
MINER_ADDRESS="${MINER_ADDRESS:-0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266}"

if [ ! -d "$DATADIR/geth" ]; then
  echo "[chain] Initializing genesis (chainId=$CHAIN_ID)..."
  geth init --datadir "$DATADIR" "$GENESIS" || { echo "[chain] genesis init failed"; exit 1; }
else
  echo "[chain] Existing datadir detected; skipping genesis init"
fi

exec geth \
  --datadir "$DATADIR" \
  --http --http.addr 0.0.0.0 --http.port 8545 \
  --http.api eth,net,web3,debug,txpool \
  --http.corsdomain '*' \
  --ws --ws.addr 0.0.0.0 --ws.port 8546 --ws.origins '*' \
  --networkid "$CHAIN_ID" \
  --nodiscover --syncmode full --gcmode archive \
  --mine --miner.etherbase "$MINER_ADDRESS" \
  --verbosity 3

