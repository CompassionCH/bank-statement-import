# Copyright 2026 Compassion CH (<https://www.compassion.ch>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.exceptions import UserError


class EdiBankFileUnsupportedHandler(models.AbstractModel):
    """End the exchange record in error, for a file that is not imported.

    It raises a UserError: the EDI framework catches it, so the record gets
    the error and its job ends.
    """

    _name = "edi.bank.file.unsupported.handler"
    _inherit = "edi.oca.handler.process"
    _description = "EDI handler: bank file not imported"

    def process(self, exchange_record):
        raise UserError(
            self.env._(
                "No import for the file %(name)s of type %(type)s: "
                "it is not a bank statement.",
                name=exchange_record.exchange_filename,
                type=exchange_record.type_id.display_name,
            )
        )
