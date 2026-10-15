# Copyright 2026 Compassion CH (<https://www.compassion.ch>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo.tools import SQL
from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)

BACKEND_TYPE_XMLID = "account_statement_import_sftp.sftp_bank_edi"
BACKEND_TYPE_CODE = "bk_sftp_imp"


def pre_init_hook(env):
    """Keep the backend type of a database where the module was uninstalled.

    The EDI backends still use the backend type, so it was not deleted. If
    its xmlid is gone, give it back: else the data file creates a second
    backend type with the same code, which is not allowed.
    """
    if not table_exists(env.cr, "edi_backend_type"):
        return
    module, name = BACKEND_TYPE_XMLID.split(".")
    if env["ir.model.data"].search_count(
        [("module", "=", module), ("name", "=", name)]
    ):
        return
    env.cr.execute(
        SQL("SELECT id FROM edi_backend_type WHERE code = %s", BACKEND_TYPE_CODE)
    )
    row = env.cr.fetchone()
    if row:
        env["ir.model.data"].create(
            {
                "module": module,
                "name": name,
                "model": "edi.backend.type",
                "res_id": row[0],
                "noupdate": True,
            }
        )
        _logger.info("Backend type %s: xmlid %s set again", row[0], BACKEND_TYPE_XMLID)


def post_init_hook(env):
    set_statement_process_handler(env)


def set_statement_process_handler(env):
    """Give a process handler to the input exchange types of the backend type.

    In v14 one component processed all input files of the backend type. In
    18 the exchange type gives the process handler. edi_oca puts its
    component handler where it is empty, but no component is left to call,
    and its error is not caught: the job would fail again every hour.

    - camt files (the filename pattern has "camt"): import bank statements.
    - Other files, like pain.002: they were never bank statements. Like in
      v14, they end once in error, with a clear message.

    Another handler, or process settings on the type, can be on purpose: we
    keep them and only report them.
    """
    backend_type = env.ref(BACKEND_TYPE_XMLID, raise_if_not_found=False)
    if not backend_type:
        return
    statement_handler = env["ir.model"]._get("edi.bank.statement.import.handler")
    unsupported_handler = env["ir.model"]._get("edi.bank.file.unsupported.handler")
    component_handler = env.ref(
        "edi_component_oca.model_edi_oca_component_handler", raise_if_not_found=False
    )
    exchange_types = (
        env["edi.exchange.type"]
        .with_context(active_test=False)
        .search(
            [
                ("direction", "=", "input"),
                # A type with a backend has the type of its backend.
                ("backend_type_id", "=", backend_type.id),
            ]
        )
    )
    camt_types = exchange_types.filtered(
        lambda t: "camt" in (t.exchange_filename_pattern or "").lower()
    )
    for types, handler in (
        (camt_types, statement_handler),
        (exchange_types - camt_types, unsupported_handler),
    ):
        to_set = types.filtered(
            lambda t: (
                not t.process_model_id or t.process_model_id == component_handler
            )
            and not _has_process_settings(t)
        )
        if to_set:
            to_set.write({"process_model_id": handler.id})
        other = types.filtered(lambda t, h=handler: t.process_model_id != h)
        _logger.info(
            "Bank statement import over EDI: %s set on input types %s",
            handler.model,
            to_set.ids,
        )
        if other:
            _logger.warning(
                "Bank statement import over EDI: input types %s keep their "
                "process handler or settings, please check them",
                other.ids,
            )


def _has_process_settings(exchange_type):
    """The component handler reads them, our handlers do not."""
    settings = exchange_type.get_settings() or {}
    return bool(
        settings.get("components", {}).get("process")
        or settings.get("execution_model", {}).get("process")
    )
