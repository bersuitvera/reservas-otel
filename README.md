# Sistema de Reservas - Microservicios

Proyecto de ejemplo con microservicios en Python/FastAPI para gestión de salas, usuarios, reservas y notificaciones, con trazabilidad distribuida en OpenSearch usando OpenTelemetry Collector y Data Prepper.

## Servicios

| Servicio | Puerto local | Descripción |
|---|---:|---|
| API Gateway | `8080` | Punto de entrada del flujo funcional. |
| Room Service | `8081` | Inventario de salas y consulta por id/capacidad. |
| User Service | `8082` | Consulta básica de usuarios. |
| Reservation Service | `8083` | Disponibilidad y creación de reservas. |
| Notification Service | `8084` | Consumidor de eventos desde Redis Streams. |
| OpenSearch API | `9200` | Almacenamiento y consulta de telemetría. |
| OpenSearch Dashboards | `5601` | Visualización de trazas, logs y métricas. |
| Data Prepper OTLP gRPC | `21890` | Entrada OTLP unificada (traces/logs/metrics). |
| Data Prepper API | `4900` | Estado operativo de pipelines. |
| OTel Collector OTLP gRPC | `4317` | Receiver OTLP gRPC desde servicios. |
| OTel Collector OTLP HTTP | `4318` | Receiver OTLP HTTP desde servicios. |
| PostgreSQL | `5432` | Persistencia de salas y reservas. |
| Redis | `6379` | Bus de eventos para notificaciones. |

## Versiones fijadas

- OpenSearch: `3.6.0`
- OpenSearch Dashboards: `3.6.0`
- Data Prepper: `2.15.0`
- OTel Collector Contrib: `0.150.1`
- PostgreSQL: `16-alpine`
- Redis: `7-alpine`

## Arquitectura definitiva

```text
[Microservicios FastAPI]
    |
    | OTLP HTTP (4318)
    v
[OTel Collector]
    |
    | OTLP gRPC (21890)
    v
[Data Prepper entry-pipeline]
    |---- route TRACE  -> traces-raw-pipeline + service-map-pipeline
    |---- route LOG    -> logs-pipeline
    \---- route METRIC -> metrics-pipeline
                     |
                     v
               [OpenSearch]
                     |
                     v
          [OpenSearch Dashboards]
```

## Modelo de datos (PostgreSQL + eventos)

### Diagrama ER (simplificado)

```text
rooms
  id (PK)
  name
  capacity
  equipment
    ^
    |
reservations
  id (PK)
  room_id
  user_id
  start_ts
  end_ts
  status
```

Nota: en esta POC `room_id` y `user_id` se validan a nivel de aplicación (no hay FK declaradas en SQL).

### Esquema de tablas

Tabla `rooms`:

- `id` `SERIAL` `PRIMARY KEY`
- `name` `TEXT NOT NULL`
- `capacity` `INT NOT NULL`
- `equipment` `TEXT NOT NULL DEFAULT ''`

Tabla `reservations`:

- `id` `SERIAL` `PRIMARY KEY`
- `room_id` `INT NOT NULL`
- `user_id` `INT NOT NULL`
- `start_ts` `TIMESTAMP NOT NULL`
- `end_ts` `TIMESTAMP NOT NULL`
- `status` `TEXT NOT NULL DEFAULT 'CONFIRMED'`

### Modelo de evento (Redis Stream `events`)

Evento publicado por `reservation-service`:

```json
{
  "type": "reservation.created",
  "reservation_id": 13,
  "room_id": 1,
  "user_id": 1,
  "trace": {
    "traceparent": "00-<trace_id>-<span_id>-01"
  }
}
```

## Flujo funcional

1. `api-gateway` valida usuario llamando a `user-service`.
2. `api-gateway` delega creación en `reservation-service`.
3. `reservation-service` valida sala contra `room-service`.
4. `reservation-service` comprueba disponibilidad y persiste reserva.
5. `reservation-service` publica evento `reservation.created` en Redis.
6. `notification-service` consume ese evento en la misma traza distribuida.

## Ejemplo de traza correcta (reserva confirmada)

```text
api-gateway
  ├── GET user-service /users/1
  │     └── respuesta 200
  │
  └── POST reservation-service /reservations
        ├── reservation.flow.create
        ├── reservation.validate.room
        │     └── GET room-service /rooms/1
        │           └── SELECT rooms WHERE id = 1
        │
        ├── reservation.check.availability
        │     └── SELECT COUNT(*) FROM reservations
        │
        ├── reservation.persist.confirmed
        │     └── INSERT INTO reservations
        │
        └── reservation.event.publish
              └── Redis XADD events
                    └── notification-service consume reservation.created
```

## Ejemplo de traza de error (conflicto 409)

```text
api-gateway
  ├── GET user-service /users/1
  │     └── user-service responde 200
  │
  └── POST reservation-service /reservations
        ├── reservation.flow.create
        ├── reservation.validate.room
        │     └── GET room-service /rooms/1
        │           └── SELECT rooms WHERE id = 1
        │
        └── reservation.check.availability
              └── SELECT COUNT(*) FROM reservations
                    → detecta conflicto
                    → reservation.conflict
                    → HTTPException 409
```

## Instrumentación y nomenclatura

La inicialización común está en `services/common/otel.py` con `setup_telemetry(service_name)`.

Instrumentación automática:

- FastAPI: spans servidor por endpoint.
- HTTPX: spans cliente entre microservicios.
- SQLAlchemy: spans de consultas SQL.
- Redis: spans de operaciones de mensajería.

Instrumentación manual de negocio (reservation/notification):

- `reservation.flow.create`
- `reservation.validate.room`
- `reservation.check.availability`
- `reservation.persist.confirmed`
- `reservation.event.publish`
- `notification.consume.reservation_created`

Todos los spans de negocio usan atributos `app_*` para evitar conflictos de mapping en OpenSearch.

## Levantar el entorno

```bash
docker compose up -d --build
```

Solo observabilidad:

```bash
docker compose up -d --force-recreate opensearch opensearch-dashboards data-prepper otel-collector
```

## Smoke test E2E

Script: `scripts/test-services.sh`

Qué valida:

1. Healthchecks de servicios.
2. Flujo funcional por `api-gateway`.
3. Búsqueda automática de franja libre (idempotente).
4. Reserva exitosa (`200`).
5. Reintento duplicado (`409`).

Uso:

```bash
bash scripts/test-services.sh
```

Parámetros útiles:

```bash
TEST_DAY=2026-05-04 bash scripts/test-services.sh
BASE_URL_GATEWAY=http://localhost:8080 bash scripts/test-services.sh
```

## Tests unitarios (servicios Python)

Se incluye una suite de unit tests en `services/tests/` con cobertura de:

- `api-gateway`
- `room-service`
- `user-service`
- `reservation-service`
- `notification-service`

Instalación de dependencias de test:

```bash
python3 -m pip install -r services/common/requirements.txt -r services/requirements-dev.txt
```

Ejecución:

```bash
pytest -q services/tests
```

Notas:

- Los tests mockean telemetría e instrumentadores para evitar exportaciones reales.
- Las dependencias externas (DB/Redis/HTTP entre servicios) se sustituyen por dobles de prueba.

## Qué comprobar en Dashboards

En Trace Analytics, tras ejecutar el smoke test:

- Traza `POST /reservations` con `200` que incluya `notification.consume.reservation_created`.
- Traza `POST /reservations` con `409` que incluya `reservation.conflict` y no publique evento.

En índices:

- Trazas: `otel-v1-apm-span-*`
- Service map: `otel-v1-apm-service-map*`
- Logs: `logs-otel-*`
- Métricas: `metrics-otel-*`

## Endpoints principales

- API Gateway: `http://localhost:8080`
- Room Service: `http://localhost:8081`
- User Service: `http://localhost:8082`
- Reservation Service: `http://localhost:8083`
- Notification Service: `http://localhost:8084`
- OTel Collector HTTP: `http://localhost:4318`
- OTel Collector gRPC: `localhost:4317`
- Data Prepper OTLP gRPC: `localhost:21890`
- Data Prepper API: `http://localhost:4900`
- OpenSearch: `http://localhost:9200`
- OpenSearch Dashboards: `http://localhost:5601`

## Documentación interna de servicios

- Detalle del código Python de prueba, responsabilidades por servicio e instrumentación:
  [`services/README.md`](./services/README.md)

## Notas operativas

- Si cambias estructura de spans/atributos y aparecen errores de parseo por mapping en trazas, recrea volumen/índices:

```bash
docker compose down -v
docker compose up -d --build
```
