.PHONY: up down reset logs seed check lint types test web-test engine-test e2e
up:    ; $(MAKE) -C infra up
down:  ; $(MAKE) -C infra down
reset: ; $(MAKE) -C infra reset
logs:  ; $(MAKE) -C infra logs
seed:  ; $(MAKE) -C infra seed
lint:  ; pnpm -r lint && cd services/engine && python -m ruff check .
types: ; pnpm -r typecheck
engine-test: ; cd services/engine && python -m pytest -q
web-test:    ; pnpm -r test
e2e:   ; pnpm --filter web e2e
check: lint types engine-test web-test
