.PHONY: install uninstall test

install:
	@echo "Installing MOA Gate..."
	@mkdir -p ~/.hermes/plugins ~/.hermes/skills/devops
	@ln -sfn $$(pwd) ~/.hermes/plugins/moa-gate
	@ln -sfn $$(pwd)/skill ~/.hermes/skills/devops/moa-adviser
	@echo "✅ Installed!"
	@echo "   Plugin: ~/.hermes/plugins/moa-gate → $$(pwd)"
	@echo "   Skill:  ~/.hermes/skills/devops/moa-adviser → $$(pwd)/skill"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Set HMAC key:  echo 'MOA_GATE_KEY=$$(openssl rand -hex 32)' >> ~/.hermes/.env"
	@echo "  2. Reload Hermes"
	@echo "  3. Try:  /moa-status"
	@echo "          /moa-adviser --help"

uninstall:
	@rm -f ~/.hermes/plugins/moa-gate
	@rm -f ~/.hermes/skills/devops/moa-adviser
	@echo "✅ Uninstalled"

test:
	@python3 -m py_compile __init__.py state.py audit.py tier.py
	@echo "✅ All files compile OK"
