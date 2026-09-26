.PHONY: up down logs test simulate

up:
	docker compose --env-file .env up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest -q

simulate:
	python3 tools/simulate.py

