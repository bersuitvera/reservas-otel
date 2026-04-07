# Sistema de Reservas - Microservicios

Proyecto de ejemplo con microservicios en Python/FastAPI para gestión de salas, usuarios, reservas y notificaciones, con PostgreSQL, Redis y trazabilidad distribuida en OpenSearch mediante Data Prepper.

## Servicios

| Servicio | Puerto local | Descripción |
|---|---:|---|
| Room Service | `8081` | Inventario de salas y filtrado por capacidad. |
| User Service | `8082` | Consulta básica de usuarios. |
| Reservation Service | `8083` | Disponibilidad y creación de reservas. |
| Notification Service | `8084` | Consumidor de eventos desde Redis Streams. |
| OpenSearch Dashboards | `5601` | Visualización de trazas distribuidas. |
| OpenSearch API | `9200` | Almacenamiento y consulta de trazas. |
| Data Prepper API | `4900` | Estado operativo del pipeline de ingestión. |
| Data Prepper Traces OTLP | `21890` | Receiver OTLP/HTTP para trazas de Trace Analytics. |
| Data Prepper Logs/Metrics OTLP | `21893` | Receiver OTLP/HTTP para logs y métricas. |
| PostgreSQL | `5432` | Persistencia de salas y reservas. |
| Redis | `6379` | Cola/event stream para notificaciones. |

## Stack técnico

- FastAPI
- SQLAlchemy
- PostgreSQL 16
- Redis 7
- OpenTelemetry
- OpenSearch
- Data Prepper
- Docker Compose

## Arquitectura General

El sistema está diseñado bajo una arquitectura de microservicios orientada a eventos para la gestión de reservas:

1. **Síncrono (API REST):** El `api-gateway` enruta las peticiones hacia `room-service`, `user-service` y `reservation-service`.
2. **Persistencia:** `room-service` y `reservation-service` mantienen su estado en esquemas separados dentro de PostgreSQL.
3. **Asíncrono (Eventos):** Al crearse una reserva en el `reservation-service`, este publica un evento en un stream de Redis. El `notification-service` consume este stream de forma asíncrona.
4. **Observabilidad:** Todos los componentes envían telemetría (Logs, Métricas, Trazas) a Data Prepper, que los formatea y envía a OpenSearch.

## Cambios relevantes

- Los servicios que acceden a PostgreSQL usan `psycopg` v3.
- La URL de conexión en Compose debe usar `postgresql+psycopg://...`.
- Las trazas se reciben en Data Prepper por OTLP/HTTP y se indexan en OpenSearch con los índices de Trace Analytics.
- OpenSearch y OpenSearch Dashboards están fijados a `3.5.0`.
- Data Prepper está fijado a `2.13.0`.
- OpenSearch y OpenSearch Dashboards se levantan sin el plugin de seguridad para simplificar el entorno local de desarrollo.

## Requisitos

- Docker
- Docker Compose
- `curl` para ejecutar el script de pruebas

## Levantar el entorno

Desde la raíz del proyecto:

```bash
docker compose up --build
```

Para recrear solo el stack de observabilidad tras cambios en el pipeline:

```bash
docker compose up -d --force-recreate opensearch opensearch-dashboards data-prepper
```

## Endpoints principales

### Room Service

- `GET http://localhost:8081/health`
- `GET http://localhost:8081/rooms`
- `GET http://localhost:8081/rooms?capacity=8`

### User Service

- `GET http://localhost:8082/health`
- `GET http://localhost:8082/users/1`

### Reservation Service

- `GET http://localhost:8083/health`
- `GET http://localhost:8083/availability?room_id=1&start=2026-03-10T10:00:00&end=2026-03-10T11:00:00`
- `POST http://localhost:8083/reservations`

Ejemplo de payload:

```json
{
  "room_id": 1,
  "user_id": 1,
  "start": "2026-03-10T10:00:00",
  "end": "2026-03-10T11:00:00"
}
```

### Notification Service

- `GET http://localhost:8084/health`

### Observabilidad

- OpenSearch Dashboards: `http://localhost:5601`
- OpenSearch API: `http://localhost:9200`
- Data Prepper API: `http://localhost:4900`
- Data Prepper Traces OTLP HTTP: `http://localhost:21890/v1/traces`
- Data Prepper Logs OTLP HTTP: `http://localhost:21893/v1/logs`
- Data Prepper Metrics OTLP HTTP: `http://localhost:21893/v1/metrics`

## Script de Pruebas (Flujo de Reservas)

Se incluye un test de integración E2E en `scripts/test-services.sh` para validar la correcta comunicación y lógica de negocio de los microservicios.

El script automatiza el siguiente flujo:

1. **Healthchecks:** Verifica que `room-service`, `user-service`, `reservation-service` y `notification-service` estén operativos (`/health`).
2. **Consultas Básicas:** Pide el catálogo de salas filtrado por capacidad y valida la existencia de un usuario.
3. **Flujo de Reserva:**
   - Consulta disponibilidad de la Sala 1 en una franja horaria (espera `available: true`).
   - Ejecuta un `POST /reservations` simulando la reserva del Usuario 1 para esa sala y franja.
   - Vuelve a consultar la disponibilidad de la Sala 1 en la misma franja (espera `available: false`).
4. **Validación de Conflictos:**
   - Intenta enviar el mismo payload de reserva de nuevo.
   - Valida que el `reservation-service` devuelva un error HTTP `409 Conflict`.

Uso:

```bash
bash scripts/test-services.sh
```

Si quieres cambiar el host base o la fecha usada:

```bash
BASE_URL_ROOM=http://localhost:8081 \
BASE_URL_USER=http://localhost:8082 \
BASE_URL_RES=http://localhost:8083 \
BASE_URL_NOTIFICATION=http://localhost:8084 \
TEST_DAY=2026-03-12 \
bash scripts/test-services.sh
```

## Reconstrucción sin caché

Si cambias dependencias o la imagen base:

```bash
docker compose build --no-cache
```

## Observabilidad

Todos los servicios exportan trazas, logs y métricas a OpenSearch mediante OpenTelemetry y Data Prepper.

- Endpoint OTLP de trazas en Compose: `http://data-prepper:21890/v1/traces`
- Endpoint OTLP de logs en Compose: `http://data-prepper:21893/v1/logs`
- Endpoint OTLP de métricas en Compose: `http://data-prepper:21893/v1/metrics`
- `setup_telemetry()` configura exportación OTLP/HTTP para trazas, logs y métricas
- Data Prepper recibe OTLP/HTTP en `/v1/traces`, `/v1/logs` y `/v1/metrics`
- OpenSearch almacena trazas en `otel-v1-apm-span-*` y `otel-v1-apm-service-map*`, logs en `logs-otel-*` y métricas en `metrics-otel-*`
- La visualización se realiza desde OpenSearch Dashboards en `http://localhost:5601`
- Room Service y Reservation Service instrumentan SQLAlchemy
- Reservation Service publica eventos en Redis Streams
- Notification Service consume esos eventos propagando el contexto de traza

### Arquitectura de Señales y Data Prepper

El proyecto establece dos vías (pipelines) de ingestión en Data Prepper para garantizar compatibilidad nativa con las herramientas de OpenSearch:

```text
[ Microservicios ]
      │
      ├─(Puerto 21890 / v1/traces)──> Pipeline Trazas ──> Índices Trace Analytics / Service Map
      │
      └─(Puerto 21893 / v1/logs|metrics)──> Pipeline General ──> Índices logs-otel-* / metrics-otel-*
```

- **Pipeline de Trazas (`21890`):** Usa el conector especializado `otel_trace_source` configurado para exportar datos hacia los sinks `otel_traces` y `service_map`. Esto es obligatorio para que los dashboards de "Trace Analytics" en OpenSearch funcionen correctamente.
- **Pipeline de Logs y Métricas (`21893`):** Usa el conector genérico `otlp`. Los microservicios mandan directamente logs y métricas por HTTP OTLP, y Data Prepper los guarda en los índices correspondientes (`logs-otel-*` y `metrics-otel-*`).

### Bootstrap de telemetry

La inicialización común está en [`services/common/otel.py`](/home/avr12s/repos/reservas/services/common/otel.py#L1) mediante `setup_telemetry(service_name)`.

Ese bootstrap configura:

- `TracerProvider` con `BatchSpanProcessor` y `OTLPSpanExporter`
- `MeterProvider` con `PeriodicExportingMetricReader` y `OTLPMetricExporter`
- `LoggerProvider` con `BatchLogRecordProcessor` y `OTLPLogExporter`
- `resource attributes` comunes:
  `service.namespace`, `service.name`, `service.version`, `service.instance.id`, `deployment.environment.name`

Todos los servicios llaman ya a `setup_telemetry()` en el arranque.

### Trazas

Las trazas combinan auto-instrumentación con algo de instrumentación manual:

- FastAPI:
  genera spans de servidor para cada request HTTP
- HTTPX:
  genera spans cliente cuando el gateway invoca otros servicios
- SQLAlchemy:
  genera spans de base de datos en `room-service` y `reservation-service`
- Redis:
  instrumenta las llamadas al cliente Redis
- spans manuales:
  añaden semántica de negocio como `reservation.create`, `reservation.publish_notification` y `notification.process`

Los spans manuales usan atributos `app_*` para evitar conflictos con mappings internos de Trace Analytics.

### Propagación de contexto entre servicios

La correlación HTTP queda resuelta por la instrumentación de FastAPI/HTTPX. El punto importante añadido en esta integración es la propagación por Redis Streams entre `reservation-service` y `notification-service`.

Flujo actual:

1. `reservation-service` crea la reserva.
2. Antes de publicar el evento en Redis, inyecta el contexto activo de OpenTelemetry en `event["trace"]`.
3. `notification-service` lee el evento, extrae ese contexto y crea un span consumidor.
4. OpenSearch puede reconstruir la relación completa entre ambos servicios y mostrarla en Trace Analytics y en el service map.

Esto es lo que hace posible ver en OpenSearch la conexión directa entre `reservation-service` y `notification-service`.

### Logs

El helper [`services/common/logger.py`](/home/avr12s/repos/reservas/services/common/logger.py#L1) hace dos cosas a la vez:

- escribe JSON estructurado por `stdout`
- emite el mismo evento al `LoggerProvider` de OpenTelemetry para exportarlo por OTLP

Cada log incluye, cuando existe un span activo:

- `trace_id`
- `span_id`
- `service`
- `level`
- `message`

Con esto los logs quedan correlables con las trazas tanto por contexto OTel como por campos explícitos en el payload JSON.

Los logs se indexan en:

- `logs-otel-*`

### Métricas

La POC añade métricas de negocio y de procesamiento para enriquecer Observability.

En `reservation-service`:

- `reservations.created`
- `reservations.conflict`
- `reservations.availability.check`
- `reservations.duration.seconds`

En `notification-service`:

- `notifications.sent`
- `notifications.failed`
- `notifications.processing.latency.ms`

Las métricas se exportan por OTLP y Data Prepper las escribe en:

- `metrics-otel-*`

### Índices resultantes en OpenSearch

Después de generar tráfico, deberías ver al menos estos índices:

- `otel-v1-apm-span-*`
- `otel-v1-apm-service-map*`
- `logs-otel-*`
- `metrics-otel-*`

Conceptualmente:

- `otel-v1-apm-span-*`:
  spans enriquecidos para Trace Analytics
- `otel-v1-apm-service-map*`:
  dependencias entre servicios
- `logs-otel-*`:
  logs estructurados exportados por OTLP
- `metrics-otel-*`:
  métricas OTEL derivadas de los servicios

### Qué validar en Dashboards

Después de levantar el entorno y ejecutar tráfico con [`scripts/test-services.sh`](/home/avr12s/repos/reservas/scripts/test-services.sh), puedes validar:

- En Trace Analytics:
  spans de `room-service`, `user-service`, `reservation-service` y `notification-service`
- En Service Map:
  relación `api-gateway -> reservation-service`
  relación `reservation-service -> notification-service`
- En Discover:
  documentos en `logs-otel-*`
- En índices o visualizaciones:
  documentos en `metrics-otel-*`

### Variables de entorno OTLP

En Compose cada servicio usa endpoints separados por señal:

- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://data-prepper:21890/v1/traces`
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://data-prepper:21893/v1/logs`
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://data-prepper:21893/v1/metrics`

Esto permite mantener trazas en el pipeline específico de Trace Analytics y logs/métricas en el pipeline OTLP unificado.

### Ficheros clave

- Bootstrap OTel:
  [`services/common/otel.py`](/home/avr12s/repos/reservas/services/common/otel.py#L1)
- Logger estructurado y correlado:
  [`services/common/logger.py`](/home/avr12s/repos/reservas/services/common/logger.py#L1)
- Pipeline Data Prepper:
  [`observability/data-prepper/pipelines/traces-pipeline.yaml`](/home/avr12s/repos/reservas/observability/data-prepper/pipelines/traces-pipeline.yaml#L1)
- Servicios instrumentados:
  [`services/reservation-service/main.py`](/home/avr12s/repos/reservas/services/reservation-service/main.py#L1)
  [`services/notification-service/main.py`](/home/avr12s/repos/reservas/services/notification-service/main.py#L1)
  [`services/api-gateway/main.py`](/home/avr12s/repos/reservas/services/api-gateway/main.py#L1)

## Troubleshooting

Si Data Prepper muestra errores `failed to parse` contra `otel-v1-apm-span-*`, normalmente hay un conflicto de mapping en los índices de trazas ya creados o una incompatibilidad entre el pipeline de trazas y el formato que espera Trace Analytics.

Tras cambiar la instrumentación o los atributos manuales de spans:

```bash
docker compose down -v
docker compose up -d --build
```

Si prefieres limpiar solo los índices de trazas en OpenSearch:

```bash
curl -XDELETE http://localhost:9200/otel-v1-apm-span-*
curl -XDELETE http://localhost:9200/otel-v1-apm-service-map-*
```
