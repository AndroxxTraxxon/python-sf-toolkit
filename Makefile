.PHONY: docs clean-docs

docs:
	cd docs && $(MAKE) html

clean-docs:
	cd docs && $(MAKE) clean
