.PHONY: dev-backend dev-frontend dev fmt

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev -- --port 3000

dev:
	@echo "Comandos disponibles:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

fmt:
	@echo "Formatters y linters se configurarán más adelante."
