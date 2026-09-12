PY := .venv/bin/python

setup:            ## create the venv and install the package with dev tools
	python3 -m venv .venv && $(PY) -m pip install -q --upgrade pip && $(PY) -m pip install -q -e ".[dev]"

demo:             ## block-0 vertical slice on the keystone scenario (terminal output)
	$(PY) -m oci demo --scenario keystone_cluster

demo-ledger:      ## the ledger showcase: a dead rocket body billing three operators
	$(PY) -m oci demo --scenario dead_rocket_body --mc 0

test:             ## acceptance tests for every module built so far
	$(PY) -m pytest -q

assumptions:      ## regenerate docs/ASSUMPTIONS.md from oci/config.py
	$(PY) -m oci assumptions

.PHONY: setup demo demo-ledger test assumptions
