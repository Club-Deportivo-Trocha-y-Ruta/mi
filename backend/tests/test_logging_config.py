"""Los logs de app.services.audit deben llegar a un handler con request_id.

Contrato: specs/041-multi-coach-governance/contracts/audit-recording.md §6 y
research.md R-27. Hoy los loggers "app.*" no tienen handler propio y sus
registros INFO se pierden en silencio bajo uvicorn; este test verifica que
el dictConfig de app.main resuelve eso y que cada registro trae un campo
``request_id`` (con "-" por defecto cuando no hay contexto de request).
"""

import logging

import app.main  # noqa: F401 — importar dispara logging.config.dictConfig


def test_audit_logger_record_reaches_handler_with_request_id():
    """Se inspeccionan directamente los handlers ya configurados por el
    dictConfig de app.main sobre el logger "app" (efectivo también para
    "app.services.audit" por jerarquía de nombres) para confirmar que el
    filtro de request_id está enganchado ahí."""
    logger = logging.getLogger("app.services.audit")
    app_logger = logging.getLogger("app")
    assert len(app_logger.handlers) >= 1
    handler = app_logger.handlers[0]

    record = logger.makeRecord(
        logger.name, logging.INFO, __file__, 0, "evento de auditoría de prueba", (), None,
    )
    for log_filter in handler.filters:
        assert log_filter.filter(record)
    assert record.request_id == "-"


def test_app_logger_has_a_handler_configured():
    """El logger "app" debe tener handler propio (no depender del
    lastResort de logging), para que INFO no se descarte en producción."""
    app_logger = logging.getLogger("app")
    assert app_logger.level == logging.INFO
    assert len(app_logger.handlers) >= 1


def test_app_logger_propagates_to_root_for_caplog():
    """propagate debe quedar en True: el logger raíz nunca recibe handlers
    propios (uvicorn no lo toca) así que dejar propagar "app" no duplica
    salida en producción, y es lo único que permite que el hook "caplog" de
    pytest —que se cuelga del logger raíz— vea los registros de app.* en
    las decenas de pruebas (varias de privacidad) que dependen de eso."""
    app_logger = logging.getLogger("app")
    assert app_logger.propagate is True
