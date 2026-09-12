PY := .venv/bin/python

setup:            ## create the venv and install the package with dev tools
	python3 -m venv .venv && $(PY) -m pip install -q --upgrade pip && $(PY) -m pip install -q -e ".[dev]"

demo:             ## block-0 vertical slice on the keystone scenario (terminal output)
	$(PY) -m oci demo --scenario keystone_cluster

demo-ledger:      ## the ledger showcase: a dead rocket body billing three operators
	$(PY) -m oci demo --scenario dead_rocket_body --mc 0

screen:           ## block 1: screen the real 700–900 km shell for 72 h (needs network once; cached after)
	$(PY) -m oci screen --alt-low 700 --alt-high 900 --hours 72

ledger:           ## the real externality ledger from the last cached run
	$(PY) -m oci ledger --threshold 1e-5

validate:         ## screener vs SOCRATES
	$(PY) -m oci validate-socrates

bench:            ## baselines B1–B4 vs OCI (SPEC §15) → docs/BENCHMARK.md
	$(PY) -m oci bench --mc 100 | tee /tmp/bench.txt

api:              ## M12: the REST API on :8000 (docs at /docs)
	$(PY) -m uvicorn oci.api.app:app --port 8000 --reload

api-safe:         ## the API in demo-safe mode: committed fixtures and cached runs only, no network
	OCI_DEMO_SAFE=1 $(PY) -m uvicorn oci.api.app:app --port 8000

ui:               ## M13: the frontend on :5173 (needs `make ui-setup` once)
	cd frontend && npm run dev

ui-setup:         ## install the frontend's dependencies
	cd frontend && npm install

ui-build:         ## production build of the frontend
	cd frontend && npm run build

dev:              ## API on :8000 and UI on :5173, together
	($(MAKE) api &) && $(MAKE) ui

demo-safe:        ## the full offline rehearsal: API + UI from fixtures, cable pulled
	OCI_DEMO_SAFE=1 $(MAKE) dev

capacity:         ## block 10: shell map + deployment table → docs/CAPACITY.md
	$(PY) -m oci capacity --offline

chaos:            ## block 11: inject a perturbation and print the replan diff
	$(PY) -m oci chaos --scenario keystone_cluster --inject NEW_OBJECT COVARIANCE_SPIKE

test:             ## acceptance tests for every module built so far
	$(PY) -m pytest -q

assumptions:      ## regenerate docs/ASSUMPTIONS.md from oci/config.py
	$(PY) -m oci assumptions

.PHONY: setup demo demo-ledger screen ledger validate bench test assumptions \
	api api-safe ui ui-setup ui-build dev demo-safe capacity chaos
