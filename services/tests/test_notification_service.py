import json
from unittest.mock import MagicMock


def _event_payload():
    return {
        b"event": json.dumps(
            {
                "type": "reservation.created",
                "reservation_id": 13,
                "room_id": 1,
                "user_id": 1,
                "trace": {"traceparent": "00-abc-def-01"},
            }
        ).encode()
    }


def test_notification_worker_success_path(service_loader):
    module = service_loader("notification-service")

    module.stop_flag = False
    module.time.sleep = lambda _: None
    module.random.random = lambda: 0.99
    module.log = MagicMock()

    module.notification_sent_counter = MagicMock()
    module.notification_failed_counter = MagicMock()
    module.notification_latency_histogram = MagicMock()

    event = _event_payload()

    class FakeRedis:
        calls = 0

        def xread(self, *args, **kwargs):
            if self.calls == 0:
                self.calls += 1
                return [(b"events", [(b"1-0", event)])]
            module.stop_flag = True
            return []

    module.redis = FakeRedis()
    module.worker()

    assert module.notification_sent_counter.add.called
    assert not module.notification_failed_counter.add.called


def test_notification_worker_failure_path(service_loader):
    module = service_loader("notification-service")

    module.stop_flag = False
    module.time.sleep = lambda _: None
    module.random.random = lambda: 0.0
    module.log = MagicMock()

    module.notification_sent_counter = MagicMock()
    module.notification_failed_counter = MagicMock()
    module.notification_latency_histogram = MagicMock()

    event = _event_payload()

    class FakeRedis:
        calls = 0

        def xread(self, *args, **kwargs):
            if self.calls == 0:
                self.calls += 1
                return [(b"events", [(b"1-0", event)])]
            module.stop_flag = True
            return []

    module.redis = FakeRedis()
    module.worker()

    assert module.notification_failed_counter.add.called


def test_notification_worker_skips_invalid_event_and_continues(service_loader):
    module = service_loader("notification-service")

    module.stop_flag = False
    module.time.sleep = lambda _: None
    module.random.random = lambda: 0.99
    module.log = MagicMock()

    module.notification_sent_counter = MagicMock()
    module.notification_failed_counter = MagicMock()
    module.notification_processing_error_counter = MagicMock()
    module.notification_latency_histogram = MagicMock()

    invalid_event = {b"event": b"not-json"}
    valid_event = _event_payload()

    class FakeRedis:
        calls = 0

        def xread(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return [(b"events", [(b"1-0", invalid_event)])]
            if self.calls == 2:
                return [(b"events", [(b"2-0", valid_event)])]
            module.stop_flag = True
            return []

    module.redis = FakeRedis()
    module.worker()

    assert module.notification_processing_error_counter.add.called
    assert module.notification_sent_counter.add.called
