.PHONY: run dev api web build test prewarm bench

run:        ## everything in one command: http://localhost:8000
	test -d .venv || (python3 -m venv .venv && .venv/bin/pip install -q -r backend/requirements.txt)
	test -f backend/static/index.html || (cd frontend && npm install --no-audit --no-fund && npx ng build)
	cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

api:        ## backend with auto-reload on :8000
	cd backend && uvicorn app.main:app --reload --port 8000

web:        ## Angular dev server on :4200 (proxies /api to :8000)
	cd frontend && npx ng serve

build:      ## build frontend into backend/static (then `make api` serves everything on :8000)
	cd frontend && npx ng build

test:
	cd backend && python -m pytest -q

prewarm:    ## run the demo examples for real and store them as seed cache
	cd backend && python -m app.prewarm

bench:
	cd backend && python -m app.benchmark
