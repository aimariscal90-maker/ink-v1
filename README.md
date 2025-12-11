# ink-v1

MVP para traducir cómics (PDF, CBR/CBZ) de inglés a castellano usando IA.

## Estructura del proyecto

- **backend/** → FastAPI + pipeline de procesamiento.
- **frontend/** → Next.js (se generará en el día 2).
- **.devcontainer/** → entorno de desarrollo optimizado para GitHub Codespaces.

## Desarrollo en Codespaces

1. Abre el repositorio en GitHub → "Create Codespace".
2. Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
