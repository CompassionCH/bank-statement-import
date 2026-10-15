# Copyright 2023 Compassion CH
# @author: Simon Gonzalez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class EdiBankStatementImportHandler(models.AbstractModel):
    """Import the file of an EDI exchange record as bank statements."""

    _name = "edi.bank.statement.import.handler"
    _inherit = "edi.oca.handler.process"
    _description = "EDI handler: import bank statement files"

    def process(self, exchange_record):
        statement_import = self.env["account.statement.import"].create(
            {
                "statement_file": exchange_record.exchange_file,
                "statement_filename": exchange_record.exchange_filename,
            }
        )
        # It raises a UserError when the file has no new transaction or
        # cannot be read: the exchange record then gets the error.
        result = statement_import._import_file()
        statements = self.env["account.bank.statement"].browse(result["statement_ids"])
        message = self.env._(
            "Imported bank statements: %(names)s",
            names=", ".join(statements.mapped("display_name")),
        )
        if result["notifications"]:
            message = "\n".join([message] + result["notifications"])
        return message
