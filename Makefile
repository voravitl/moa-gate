.PHONY: install uninstall test install-hook uninstall-hook

install:
	@bash scripts/install.sh

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


## AI-DLC Compass

install-ai-dlc:
	@bash ai-dlc/scripts/install.sh

uninstall-ai-dlc:
	@rm -f ~/.hermes/plugins/ai-dlc
	@rm -rf ~/.hermes/ai-dlc
	@echo "✅ AI-DLC Compass uninstalled"

test-ai-dlc:
	@python3 -m py_compile ai-dlc/__init__.py ai-dlc/steering/registry.py ai-dlc/engine/phase.py ai-dlc/engine/verifier.py
	@echo "✅ All AI-DLC files compile OK"

verify-ai-dlc:
	@python3 -c "import sys; sys.path.insert(0, 'ai-dlc'); from steering.registry import load_rules; r = load_rules(); print(f'Loaded {sum(len(v) for v in r.values())} rules across {len(r)} categories')"

lint-ai-dlc:
	@bash -n ai-dlc/scripts/install.sh && echo "✅ Installer syntax OK"
