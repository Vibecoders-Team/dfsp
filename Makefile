.PHONY: hooks hooks.uninstall

hooks:
	@chmod +x .githooks/* 2>/dev/null || true
	@git config core.hooksPath .githooks
	@echo "✔ Git hooks enabled (core.hooksPath=.githooks)"

hooks.uninstall:
	@git config --unset core.hooksPath || true
	@echo "✔ Git hooks disabled"
