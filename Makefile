.PHONY: install uninstall test install-hook uninstall-hook

install: install-hook
	@echo "Installing MOA Gate..."
	@mkdir -p ~/.hermes/plugins ~/.hermes/skills/devops
	@ln -sfn $$(pwd) ~/.hermes/plugins/moa-gate
	@ln -sfn $$(pwd)/skill ~/.hermes/skills/devops/moa-adviser
	@echo "✅ Installed!"
	@echo "   Plugin: ~/.hermes/plugins/moa-gate → $$(pwd)"
	@echo "   Skill:  ~/.hermes/skills/devops/moa-adviser → $$(pwd)/skill"
	@echo "   Hook:   git config core.hooksPath (global add)"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Set HMAC key:  echo 'MOA_GATE_KEY=$$(openssl rand -hex 32)' >> ~/.hermes/.env"
	@echo "  2. Reload Hermes"
	@echo "  3. Try:  /moa-status"
	@echo "          /moa-adviser --help"

uninstall: uninstall-hook
	@rm -f ~/.hermes/plugins/moa-gate
	@rm -f ~/.hermes/skills/devops/moa-adviser
	@echo "✅ Uninstalled"

install-hook:
	@echo "Installing MOA Gate pre-commit hook..."
	@mkdir -p ~/.hermes/moa-gate
	@cp hooks/pre-commit.py ~/.hermes/moa-gate/pre-commit.py
	@chmod +x ~/.hermes/moa-gate/pre-commit.py
	@git config --global core.hooksPath ~/.hermes/moa-gate/ 2>/dev/null || true
	@echo "✅ Pre-commit hook installed (global: core.hooksPath)"
	@echo "   All git repos will now check MOA Gate before every commit."

uninstall-hook:
	@echo "Removing MOA Gate pre-commit hook..."
	@rm -f ~/.hermes/moa-gate/pre-commit.py
	-@git config --global --unset core.hooksPath 2>/dev/null || true
	@echo "✅ Pre-commit hook uninstalled"

test:
	@python3 -m py_compile __init__.py state.py audit.py tier.py
	@echo "✅ All files compile OK"
