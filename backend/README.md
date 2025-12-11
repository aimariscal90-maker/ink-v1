# Comic Translator Backend

API backend para la aplicación de traductor de cómics.

## Estructura del proyecto

```
app/
├── api/          # Rutas y endpoints de la API
├── core/         # Configuración central
├── models/       # Modelos de datos
└── main.py       # Entrada de la aplicación
```

## Instalación

```bash
pip install -r requirements.txt
```

## Desarrollo

```bash
uvicorn app.main:app --reload
```
