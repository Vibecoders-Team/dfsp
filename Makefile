.PHONY: hooks hooks.uninstall ngrok.up ngrok.sync dev.up

hooks:
	@chmod +x .githooks/* 2>/dev/null || true
	@git config core.hooksPath .githooks
	@echo "✔ Git hooks enabled (core.hooksPath=.githooks)"

hooks.uninstall:
	@git config --unset core.hooksPath || true
	@echo "✔ Git hooks disabled"

ngrok.up:
	docker compose --env-file ./deploy/.env.local -f compose.dev.yml up -d ngrok
	@echo "✔ ngrok started (see http://localhost:4040)"

dev.up: ngrok.up
	@echo "→ Sync ngrok URL into deploy/.env.local"
	@chmod +x scripts/ngrok_sync.sh && ./scripts/ngrok_sync.sh --no-restart
	@echo "→ Starting full stack with env-file deploy/.env.local"
	docker compose --env-file ./deploy/.env.local -f compose.dev.yml up -d
	@echo "✔ Dev stack running"

ngrok.sync:
	chmod +x scripts/ngrok_sync.sh
	./scripts/ngrok_sync.sh
