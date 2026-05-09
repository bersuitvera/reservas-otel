# Reservation Service

Este microservicio es el núcleo transaccional del sistema. Se encarga de gestionar la disponibilidad de las salas, confirmar las reservas en base de datos y emitir eventos asíncronos para los sistemas downstream (como el envío de notificaciones).

## Responsabilidades Principales

1. **Validación de Entidades**: Asegurar que las salas existen consultando al `room-service`.
2. **Control de Disponibilidad**: Verificar de forma síncrona que no existan solapamientos de horarios para una sala específica (`reservation.check.availability`).
3. **Persistencia Transaccional**: Almacenar la reserva con estado `CONFIRMED` en PostgreSQL.
4. **Publicación de Eventos**: Propagar la confirmación mediante Redis Streams (`events`), inyectando `traceparent` para continuidad de trazas en Elastic APM.

## Endpoints

- `GET /availability`: Consulta de franjas libres. Recibe `room_id`, `start` y `end`.
- `POST /reservations`: Creación de la reserva. Devuelve HTTP 200 en éxito o HTTP 409 si hay conflicto de horario.
- `GET /reservations/{reservation_id}`: Consulta del estado de una reserva específica.
- `GET /health`: Sonda de liveness/readiness.

## Modelo de Datos (PostgreSQL)

La persistencia principal ocurre en la tabla `reservations` de la base de datos `reservas_db`:

| Campo      | Tipo        | Descripción                                   |
|------------|-------------|-----------------------------------------------|
| `id`       | SERIAL (PK) | Identificador único de la reserva.            |
| `room_id`  | INT         | Identificador lógico de la sala.              |
| `user_id`  | INT         | Identificador lógico del usuario.             |
| `start_ts` | TIMESTAMP   | Fecha y hora de inicio de la reserva.         |
| `end_ts`   | TIMESTAMP   | Fecha y hora de fin de la reserva.            |
| `status`   | TEXT        | Estado de la reserva (ej. `CONFIRMED`).       |

> **Nota:** La integridad referencial de `room_id` y `user_id` es lógica y distribuida, ya que las entidades maestras viven (o son expuestas) a través de otros microservicios.

## Eventos Emitidos (Redis Stream)

Tras una reserva exitosa, se publica un mensaje en el stream `events` de Redis.

**Payload del evento:**
```json
{
  "type": "reservation.created",
  "reservation_id": "<id_db>",
  "room_id": "<room_id>",
  "user_id": "<user_id>",
  "trace": {
    "traceparent": "00-<trace_id>-<span_id>-01"
  }
}
```
El campo `traceparent` permite que `notification-service` continúe la traza distribuida en el mismo contexto.

## Instrumentación y Observabilidad

Este servicio utiliza instrumentación intensiva, tanto automática como manual.

### Spans Manuales (Negocio)

- `reservation.flow.create`: Span padre de la operación de creación.
- `reservation.validate.room`: Envoltorio de la llamada HTTP a `room-service`.
- `reservation.check.availability`: Operación de lectura transaccional en la BD.
- `reservation.persist.confirmed`: Operación de inserción en BD (`INSERT`).
- `reservation.event.publish`: Inyección de contexto y escritura en Redis (`PRODUCER`).

### Eventos de Trazas

- `reservation.conflict`: Añadido al span cuando la consulta de disponibilidad detecta un solapamiento (resultando en un 409).

### Métricas

Las métricas de servicio/proceso de la aplicación son capturadas por el agente APM.  
Las métricas de infraestructura se recogen con Elastic Agent.

## Gestión de Errores y Concurrencia

El sistema previene "Double Booking" asegurándose de que la comprobación de disponibilidad y la inserción se manejen considerando el solapamiento de fechas. Si se detecta un registro conflictivo, se detiene el flujo transaccional y se retorna un `HTTPException(409)`.
