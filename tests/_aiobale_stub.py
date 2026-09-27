"""aiobale stub for local testing.

The aiobale package on PyPI is an empty shell (Enalite/aiobale GitHub repo was
taken down). The mirror we install on the VPS (mehrad1232/Aiobale) is not
pinned to a public release, so we don't want CI to depend on it. The
production code lazy-imports aiobale; this stub lets the import succeed
during unit tests so we can verify non-aiobale logic in isolation.

Replace this with the real aiobale when a stable release is back on PyPI.
"""

from types import SimpleNamespace


class ChatType:
    PRIVATE = "private"


class _Stub:
    def __init__(self, *a, **kw):
        pass

    def __getattr__(self, name):
        return _Stub()

    def __call__(self, *a, **kw):
        return _Stub()


Client = _Stub
Dispatcher = _Stub

# Submodule layout used by production code
enums = SimpleNamespace(ChatType=ChatType)
