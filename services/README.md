# Services (Código Python de Prueba)

Este directorio contiene los microservicios FastAPI del laboratorio y su instrumentación OpenTelemetry.

## Estructura

- `api-gateway/`: orquesta el flujo de negocio.
- `room-service/`: catálogo de salas.
- `user-service/`: consulta de usuarios.
- `reservation-service/`: disponibilidad y creación de reservas.
- `notification-service/`: consumo asíncrono de eventos.
- `common/otel.py`: bootstrap común de telemetría.
- `common/logger.py`: logging JSON correlado con trazas.

## Arquitectura de ejecución

```text
api-gateway
  ├── user-service
  └── reservation-service
        ├── room-service
        ├── PostgreSQL
        └── Redis (XADD events)
              └── notification-service (XREAD events)
```

## Modelo de datos 

### PostgreSQL

`rooms`:

- `id` (PK), `name`, `capacity`, `equipment`

`reservations`:

- `id` (PK), `room_id`, `user_id`, `start_ts`, `end_ts`, `status`

Relación funcional:

- `reservations.room_id` referencia lógicamente a `rooms.id` (validación en aplicación).

### Redis Stream (`events`)

Evento principal emitido:

- `type: reservation.created`
- `reservation_id`
- `room_id`
- `user_id`
- `trace.traceparent` (propagación OpenTelemetry)

## Instrumentación común (`common/otel.py`)

Todos los servicios llaman a `setup_telemetry(SERVICE_NAME)` al arrancar.

Configura:

- `TracerProvider` + `BatchSpanProcessor` + `OTLPSpanExporter`
- `MeterProvider` + `PeriodicExportingMetricReader` + `OTLPMetricExporter`
- `LoggerProvider` + `BatchLogRecordProcessor` + `OTLPLogExporter`
- `Resource` común:
  - `service.namespace`
  - `service.name`
  - `service.version`
  - `service.instance.id`
  - `deployment.environment.name`

## Logging correlado (`common/logger.py`)

`log(level, msg, **fields)`:

- imprime JSON estructurado por `stdout`
- añade `trace_id` y `span_id` del span activo
- reemite al logger de OpenTelemetry (misma señal de logs)

Esto permite correlación directa logs-trazas en OpenSearch.

## Servicios

### 1) `api-gateway`

Archivo: `api-gateway/main.py`

Responsabilidad:

- punto de entrada HTTP para clientes
- enruta peticiones hacia servicios internos
- valida usuario antes de crear reserva

Endpoints:

- `GET /rooms` -> `room-service /rooms`
- `GET /availability` -> `reservation-service /availability`
- `POST /reservations`
  - valida `user_id` en `user-service /users/{id}`
  - delega creación en `reservation-service /reservations`
- `GET /health`

Instrumentación:

- automática FastAPI (`FastAPIInstrumentor`)
- automática HTTPX (`HTTPXClientInstrumentor`)

### 2) `room-service`

Archivo: `room-service/main.py`

Responsabilidad:

- mantener y exponer catálogo de salas
- servir validación de sala por id para reservas

Persistencia:

- PostgreSQL (`rooms`)
- seed opcional en startup (`STARTUP_SEED=true`)

Endpoints:

- `GET /rooms` (filtro opcional `capacity`)
- `GET /rooms/{room_id}`
- `GET /health`

Instrumentación:

- automática FastAPI
- automática SQLAlchemy (`SQLAlchemyInstrumentor`)

### 3) `user-service`

Archivo: `user-service/main.py`

Responsabilidad:

- exponer usuarios demo para validación funcional

Endpoints:

- `GET /users/{user_id}`
- `GET /health`

Instrumentación:

- automática FastAPI

### 4) `reservation-service`

Archivo: `reservation-service/main.py`

Responsabilidad:

- comprobar disponibilidad de salas
- crear reservas confirmadas
- publicar evento `reservation.created` en Redis

Persistencia y dependencias:

- PostgreSQL (`reservations`)
- HTTP a `room-service` para validar sala
- Redis Stream `events` para publicación

Endpoints:

- `GET /availability`
- `POST /reservations`
- `GET /reservations/{reservation_id}`
- `GET /health`

Spans manuales de negocio:

- `reservation.flow.create`
- `reservation.validate.room`
- `reservation.check.availability`
- `reservation.persist.confirmed`
- `reservation.event.publish` (tipo `PRODUCER`)

Eventos de error:

- en conflicto de franja añade `reservation.conflict` y responde `409`

Métricas de negocio:

- `reservations.created`
- `reservations.conflict`
- `reservations.availability.check`
- `reservations.duration.seconds`

Instrumentación automática adicional:

- FastAPI
- SQLAlchemy
- HTTPX
- Redis

Propagación asíncrona de contexto:

- antes de publicar, inyecta contexto OTel en `event["trace"]`
- incluye `traceparent` que luego consume `notification-service`

### 5) `notification-service`

Archivo: `notification-service/main.py`

Responsabilidad:

- consumir stream Redis `events`
- procesar evento de reserva de forma asíncrona

Modelo de ejecución:

- worker en hilo daemon con `XREAD`
- extracción de contexto desde `event["trace"]`

Span manual principal:

- `notification.consume.<event_type>` (tipo `CONSUMER`)
  - ejemplo actual: `notification.consume.reservation_created`

Métricas:

- `notifications.sent`
- `notifications.failed`
- `notifications.processing.latency.ms`

Instrumentación automática:

- FastAPI
- Redis

## Trazas esperadas

### Flujo correcto (`POST /reservations` -> `200`)

```text
api-gateway
  ├── GET user-service /users/1
  └── POST reservation-service /reservations
        ├── reservation.flow.create
        ├── reservation.validate.room
        ├── reservation.check.availability
        ├── reservation.persist.confirmed
        └── reservation.event.publish
              └── notification.consume.reservation_created
```

### Flujo de error (`POST /reservations` duplicado -> `409`)

```text
api-gateway
  ├── GET user-service /users/1
  └── POST reservation-service /reservations
        ├── reservation.flow.create
        ├── reservation.validate.room
        └── reservation.check.availability
              └── reservation.conflict + HTTPException 409
```

## Convenciones importantes

- Los atributos de negocio usan prefijo `app_*` para minimizar conflictos de mapping.
- La ruta principal de demo y test funcional es por `api-gateway`, no por servicios aislados.
- El script `../scripts/test-services.sh` valida ambos escenarios (éxito y conflicto).

## Unit tests

Los test  están en `services/tests/` y cubren endpoints y lógica de negocio de todos los servicios.

Instalar dependencias:

```bash
python3 -m pip install -r common/requirements.txt -r requirements-dev.txt
```

Ejecutar tests:

```bash
pytest -q tests
```

