"""Almacén global de Jobs en memoria.

En este MVP no hay base de datos, así que exponemos una instancia única de
`JobService` que vive mientras el proceso está en marcha. Esto simplifica el
uso en los routers y servicios sin requerir inyección de dependencias.
"""

from app.services.job_service import JobService

# Instancia global única para toda la app (MVP en memoria)
job_service = JobService()
