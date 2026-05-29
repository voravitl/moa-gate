.PHONY: install uninstall test verify

install:
	@bash scripts/install.sh

uninstall:
	@rm -f ~/.hermes/plugins/ai-dlc
	@rm -rf ~/.hermes/ai-dlc
	@echo "\u2705 AI-DLC Compass uninstalled"

test:
	@python3 -m py_compile __init__.py steering/registry.py engine/phase.py engine/verifier.py
	@echo "\u2705 All files compile OK"

verify:
	@python3 -c "import sys; sys.path.insert(0, '.'); from steering.registry import load_rules; r = load_rules(); print(f'Loaded {sum(len(v) for v in r.values())} rules across {len(r)} categories')"
