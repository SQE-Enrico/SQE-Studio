PYTHON ?= python

.PHONY: setup demo test doctor tolerance
setup:
	$(PYTHON) scripts/bootstrap.py
demo:
	$(PYTHON) -m sqw run --out build/demo
test:
	$(PYTHON) -m unittest discover -s tests -v
doctor:
	$(PYTHON) -m sqw doctor
tolerance:
	$(PYTHON) -m sqw tolerance --out build/tolerance
