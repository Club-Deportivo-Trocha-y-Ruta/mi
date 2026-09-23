"""Pre-ping sobre un socket que el servidor MySQL ya cerró.

aiomysql/uvloop lanza ``RuntimeError("... the handler is closed")`` en vez
de un error DBAPI, y ``_do_ping_w_event`` de SQLAlchemy solo atrapa errores
DBAPI: sin el envoltorio de ``app.database`` la request reventaba con 500 en
vez de reconectar.
"""
import pytest

from app.database import _wrap_ping_closed_transport


class _Dialect:
    def __init__(self, exc: BaseException | None) -> None:
        self._exc = exc

    def do_ping(self, dbapi_connection: object) -> bool:
        if self._exc is not None:
            raise self._exc
        return True


def test_ping_on_closed_transport_reports_disconnect() -> None:
    dialect = _Dialect(
        RuntimeError("unable to perform operation on <TCPTransport closed=True>; the handler is closed")
    )
    _wrap_ping_closed_transport(dialect)

    assert dialect.do_ping(object()) is False


def test_ping_on_healthy_connection_passes_through() -> None:
    dialect = _Dialect(None)
    _wrap_ping_closed_transport(dialect)

    assert dialect.do_ping(object()) is True


def test_unrelated_runtime_error_still_raises() -> None:
    dialect = _Dialect(RuntimeError("otra cosa"))
    _wrap_ping_closed_transport(dialect)

    with pytest.raises(RuntimeError, match="otra cosa"):
        dialect.do_ping(object())
