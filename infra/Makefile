# Run from repo root: make -C infra <target>   (or `make` via the root Makefile)
COMPOSE=docker compose -f docker-compose.yml
up:      ; $(COMPOSE) up --build
down:    ; $(COMPOSE) down
reset:   ; $(COMPOSE) down -v
logs:    ; $(COMPOSE) logs -f
seed:    ; $(COMPOSE) exec web node prisma/seed.mjs
