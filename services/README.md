# Aplicación de reservas - servicios Python (POC Elastic)

Este directorio contiene los microservicios FastAPI de la POC de reservas. En esta rama la instrumentación no usa OpenTelemetry dentro de la aplicación: las trazas y transacciones se generan con Elastic APM Python Agent, mientras que Elastic Agent se encarga de recolectar logs de contenedores y métricas de infraestructura desde Docker.

## Estructura

- `api-gateway/`: entrada HTTP y orquestación.
- `room-service/`: catálogo de salas.
- `user-service/`: validación de usuarios demo.
- `reservation-service/`: disponibilidad y creación de reservas.
- `notification-service/`: consumidor asíncrono de eventos.
- `common/apm.py`: bootstrap compartido de APM.
- `common/logger.py`: logging ECS JSON.

## Stack de observabilidad usado por la app

```text
FastAPI services
  ├── Elastic APM Python Agent -> apm-server:8200 -> Elasticsearch
  └── stdout ECS JSON logs -----> Elastic Agent ----> Elasticsearch

Docker host / containers -------> Elastic Agent ----> Elasticsearch
Kibana -------------------------> Elasticsearch
```

El `docker-compose.yml` de la raíz inyecta las variables `ELASTIC_APM_*` en cada microservicio y monta la configuración standalone de Elastic Agent desde `observability/elastic-agent/elastic-agent.yml`.

## Arquitectura de ejecución

```text
api-gateway
  ├── user-service
  └── reservation-service
        ├── room-service
        ├── PostgreSQL
        └── Redis (stream events)
              └── notification-service (worker XREAD)
```

## Instrumentación de aplicación con Elastic APM

Todos los servicios inicializan APM con:

- `setup_apm(SERVICE_NAME, app)` en `common/apm.py`.

Qué hace:

- activa auto-instrumentación de librerías compatibles,
- registra middleware APM en FastAPI,
- configura el cliente desde variables `ELASTIC_APM_*`.

En esta aplicación, Elastic APM captura automáticamente tráfico HTTP entrante, llamadas HTTPX, operaciones SQLAlchemy y Redis cuando la librería es compatible. Además, `reservation-service` y `notification-service` añaden spans/transacciones manuales de negocio para que la traza represente el flujo real de reserva.

## Logs y métricas con Elastic Agent

`common/logger.py` define `log(level, msg, **fields)` y:

- formatea en ECS JSON,
- escribe por `stdout`,
- añade metadatos de servicio para consulta y correlación.

Elastic Agent no instrumenta el código Python en esta rama. Su papel es operativo:

- leer los logs Docker de los contenedores,
- decodificar el JSON ECS emitido por la aplicación,
- enviar logs a Elasticsearch,
- recolectar métricas de sistema y Docker.

La correlación entre logs y trazas depende de los campos ECS que emiten el logger y el agente APM, como `service.name`, `trace.id` y `span.id`.

## Servicios

### `api-gateway/main.py`

Responsabilidad:

- exponer endpoints públicos,
- validar usuario en `user-service`,
- delegar creación de reserva en `reservation-service`.

Endpoints:

- `GET /rooms`
- `GET /availability`
- `POST /reservations`
- `GET /health`

### `room-service/main.py`

Responsabilidad:

- exponer inventario de salas,
- responder por sala concreta.

Persistencia:

- PostgreSQL (`rooms`), con seed opcional (`STARTUP_SEED=true`).

Endpoints:

- `GET /rooms`
- `GET /rooms/{room_id}`
- `GET /health`

### `user-service/main.py`

Responsabilidad:

- exponer usuarios demo para validación funcional.

Endpoints:

- `GET /users/{user_id}`
- `GET /health`

### `reservation-service/main.py`

Responsabilidad:

- validar sala,
- verificar solape horario,
- crear reserva,
- publicar evento en Redis.

Dependencias:

- PostgreSQL,
- HTTP hacia `room-service`,
- Redis stream `events`.

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
- `reservation.event.publish`

### `notification-service/main.py`

Responsabilidad:

- consumir stream Redis,
- procesar eventos de reserva,
- mantener continuidad de traza entre publicación y consumo.

Modelo:

- worker en hilo daemon,
- `XREAD` bloqueante,
- transacción APM por evento procesado.
- continuación de traza mediante el `traceparent` propagado en el evento Redis.

Span principal:

- `notification.consume.<event_type>`

Endpoint:

- `GET /health`

## Flujo esperado de trazas

### Caso exitoso (`POST /reservations` -> `200`)

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

### Caso conflicto (`POST /reservations` repetido -> `409`)

```text
api-gateway
  ├── GET user-service /users/1
  └── POST reservation-service /reservations
        ├── reservation.flow.create
        ├── reservation.validate.room
        └── reservation.check.availability
              └── reservation.conflict + HTTP 409
```

## Convenciones

- Etiquetas de negocio con prefijo `app_*`.
- Ruta funcional principal de pruebas: `api-gateway`.
- El script `../scripts/test-services.sh` valida tanto éxito como conflicto.

## Tests

- Unit tests principales en `services/tests/`.
- Se mockea APM para no depender de infraestructura en pruebas unitarias.
