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


### CORS y desarrollo

- Para desarrollo, la API permite configurar los orígenes CORS mediante la variable `ALLOWED_ORIGINS` en `backend/.env` (ver `backend/.env.example`).
- Para usar Codespaces, copia `backend/.env.example` → `backend/.env` y rellena `ALLOWED_ORIGINS` con las URLs de tu Codespace. Ejemplos:
	- `http://localhost:5173` (Vite local)
	- `https://<CODESPACE>-5173.app.github.dev` (Codespaces frontend URL)
	- `https://<CODESPACE>-8000.app.github.dev` (Codespaces backend URL)
- Si usas el frontend con Vite localmente, en `frontend/vite.config.ts` hay una regla `proxy` que reenvía `/api` a `http://127.0.0.1:8000`, evitando posibles problemas de CORS en desarrollo.

```

## Progreso del pipeline

- El backend expone `progress_current`, `progress_total` y `progress_stage` en el endpoint de estado `/api/v1/jobs/{job_id}`.
- Las etapas reportadas son: `import`, `ocr`, `translate`, `render`, `export` y `completed`.
- El frontend muestra un texto contextual (p. ej. "OCR 3 / 24") y una barra de progreso calculada a partir de estos campos.

### Tests

```bash
cd backend
pytest
```
