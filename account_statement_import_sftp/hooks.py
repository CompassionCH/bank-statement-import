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
    """Use the bank statement handler to process the camt input files.

    In v14 a component processed all input files of the backend type. In 18
    the exchange type gives the process handler. edi_oca puts its component
    handler where it is empty, but no component is left to call.

    Only camt files (the filename pattern has "camt"): other files, like the
    pain.002 ones, were never bank statements and always failed. Another
    handler can be on purpose, so we keep it and only report it.
    """
    backend_type = env.ref(BACKEND_TYPE_XMLID, raise_if_not_found=False)
    if not backend_type:
        return
    handler = env["ir.model"]._get("edi.bank.statement.import.handler")
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
    to_set = camt_types.filtered(
        lambda t: not t.process_model_id or t.process_model_id == component_handler
    )
    if to_set:
        to_set.write({"process_model_id": handler.id})
    other = camt_types.filtered(lambda t: t.process_model_id != handler)
    _logger.info(
        "Bank statement import over EDI: %s camt input types, handler set on %s, "
        "other input types not changed: %s",
        len(camt_types),
        to_set.ids,
        (exchange_types - camt_types).ids,
    )
    if other:
        _logger.warning(
            "Bank statement import over EDI: camt input types %s have another "
            "process handler, please check them",
            other.ids,
        )
