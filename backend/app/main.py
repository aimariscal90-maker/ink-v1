from fastapi import FastAPI

app = FastAPI(
    title="Ink API",
    version="0.1.0",
    description="Base API bootstrap for Ink Comic Translator."
)

@app.get("/", tags=["root"])
def read_root() -> dict:
    return {"message": "Welcome to the Ink API!"}

@app.get("/health", tags=["health"])
def health_check() -> dict:
    return {"status": "ok"}
