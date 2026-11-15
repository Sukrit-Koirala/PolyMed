.PHONY: dev seed test reset-demo stop
dev:
	docker compose up --build -d
seed:
	docker compose exec backend python -m backend.app.cli seed
test:
	docker compose exec backend python -m pytest -q
reset-demo:
	@echo "Open Demo workspace as admin, choose Reset demo, and confirm RESET SYNTHETIC DEMO."
stop:
	docker compose down
