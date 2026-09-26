.PHONY: dev api web build test prewarm bench

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
