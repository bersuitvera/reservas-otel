import importlib.util
import sys
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

SERVICES_DIR = Path(__file__).resolve().parents[1]

# Permite que los módulos de servicio resuelvan "from common import ..."
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))


def load_service_module(service_name: str):
    module_path = SERVICES_DIR / service_name / "main.py"
    module_name = f"test_{service_name.replace('-', '_')}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def patch_telemetry(monkeypatch):
    # Evita exportaciones reales y dependencias de infraestructura en unit tests.
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    with ExitStack() as stack:
        stack.enter_context(patch("common.apm.setup_apm"))
        yield


@pytest.fixture
def service_loader():
    return load_service_module
