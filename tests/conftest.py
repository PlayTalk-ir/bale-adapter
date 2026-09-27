"""Pytest fixtures and aiobale guard."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tests.fake_bale import FakeBaleClient, FakeDispatcher  # noqa: E402


def _install_fake_aiobale() -> None:
    if "aiobale" in sys.modules and getattr(sys.modules["aiobale"], "_bale_test_fake", False):
        return
    mod = ModuleType("aiobale")
    mod._bale_test_fake = True  # type: ignore[attr-defined]
    mod.Client = FakeBaleClient
    mod.Dispatcher = FakeDispatcher
    enums = ModuleType("aiobale.enums")
    enums.ChatType = SimpleNamespace(PRIVATE="private")
    sys.modules["aiobale"] = mod
    sys.modules["aiobale.enums"] = enums


_install_fake_aiobale()


@pytest.fixture(autouse=True)
def _reset_fake_client():
    FakeBaleClient.instances.clear()
    yield
    FakeBaleClient.instances.clear()


@pytest.fixture
def fake_client() -> FakeBaleClient:
    c = FakeBaleClient()
    return c


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Fail if a test imports real aiobale Client outside our fake."""
    import aiobale  # noqa: F401

    assert getattr(aiobale, "_bale_test_fake", False), (
        "tests must use fake aiobale — real Client construction is forbidden"
    )
