# Copyright 2026 Compassion CH (<https://www.compassion.ch>)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
from datetime import date

from odoo.modules.migration import load_script
from odoo.tests import tagged
from odoo.tools import convert_file, mute_logger
from odoo.tools.misc import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from ..hooks import pre_init_hook, set_statement_process_handler


@tagged("post_install", "-at_install")
class TestBankStatementImportHandler(AccountTestInvoicingCommon):
    """Process EDI exchange records with the handler. No server is used."""

    @classmethod
    def setUpClass(cls):
        # The chart of accounts gives the suspense account of the journal.
        super().setUpClass()
        # Like the EDI crons and jobs, which run as superuser.
        cls.env = cls.env(su=True)
        eur = cls.env.ref("base.EUR")
        eur.active = True
        bank_account = cls.env["res.partner.bank"].create(
            {
                "acc_number": "NL12ABCD3456789012",
                "partner_id": cls.env.company.partner_id.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Bank Journal - (test sftp)",
                "code": "TBNKSFTP",
                "type": "bank",
                "bank_account_id": bank_account.id,
                "currency_id": eur.id,
            }
        )
        cls.backend_type = cls.env.ref("account_statement_import_sftp.sftp_bank_edi")
        cls.backend = cls.env["edi.backend"].create(
            {"name": "Test bank SFTP", "backend_type_id": cls.backend_type.id}
        )
        cls.handler = cls.env["ir.model"]._get("edi.bank.statement.import.handler")
        cls.unsupported_handler = cls.env["ir.model"]._get(
            "edi.bank.file.unsupported.handler"
        )
        cls.exchange_type = cls._create_type("test_camt053_in", r"^camt\.053.*\.xml")
        cls.exchange_type.process_model_id = cls.handler
        with file_open(
            "account_statement_import_sftp/tests/samples/camt053.xml", "rb"
        ) as f:
            cls.camt_file = base64.b64encode(f.read())

    @classmethod
    def _create_type(cls, code, pattern):
        return cls.env["edi.exchange.type"].create(
            {
                "name": code,
                "code": code,
                "backend_type_id": cls.backend_type.id,
                "direction": "input",
                "exchange_filename_pattern": pattern,
            }
        )

    def _process(self, file_content, filename="camt.053-test.xml", exchange_type=None):
        record = self.backend.create_record(
            (exchange_type or self.exchange_type).code,
            {
                "exchange_file": file_content,
                "exchange_filename": filename,
                "edi_exchange_state": "input_received",
            },
        )
        self.backend.exchange_process(record)
        return record

    def test_process_imports_statement(self):
        record = self._process(self.camt_file)

        self.assertEqual(record.edi_exchange_state, "input_processed")
        statement = self.env["account.bank.statement"].search(
            [("name", "=", "5678ABC/1")]
        )
        self.assertEqual(len(statement), 1)
        self.assertEqual(statement.journal_id, self.journal)
        self.assertEqual(statement.balance_start, 75000.0)
        self.assertEqual(statement.balance_end, 73800.0)
        self.assertEqual(statement.date, date(2024, 3, 2))
        self.assertEqual(statement.line_ids.amount, -1200.0)
        # The statement lines are posted when they are created.
        self.assertEqual(statement.line_ids.move_id.state, "posted")
        self.assertEqual(statement.attachment_ids.name, "camt.053-test.xml")

    def test_process_file_without_transaction(self):
        """A file without transaction gives no statement: an error."""
        content = base64.b64decode(self.camt_file).decode()
        start, end = content.index("<Ntry>"), content.index("</Ntry>") + len("</Ntry>")
        empty_file = base64.b64encode((content[:start] + content[end:]).encode())
        record = self._process(empty_file)
        self.assertEqual(record.edi_exchange_state, "input_processed_error")
        self.assertIn("already imported", record.exchange_error)

    @mute_logger(
        "odoo.addons.account_statement_import_camt.models.account_statement_import"
    )
    def test_process_unknown_format(self):
        record = self._process(base64.b64encode(b"<Document>not camt</Document>"))
        self.assertEqual(record.edi_exchange_state, "input_processed_error")
        self.assertTrue(record.exchange_error)
        self.assertFalse(
            self.env["account.bank.statement"].search(
                [("journal_id", "=", self.journal.id)]
            )
        )

    def test_process_unsupported_file_fails_once(self):
        """A pain.002 file ends in error, and the job does not fail."""
        pain002 = self._create_type("test_pain002_in", r"^pain\.002-EPO_.*\.xml")
        pain002.process_model_id = self.unsupported_handler
        record = self._process(
            base64.b64encode(b"<Document>pain.002</Document>"),
            filename="pain.002-EPO_test.xml",
            exchange_type=pain002,
        )
        self.assertEqual(record.edi_exchange_state, "input_processed_error")
        self.assertIn("not a bank statement", record.exchange_error)

    def test_set_handlers(self):
        component_handler = self.env.ref(
            "edi_component_oca.model_edi_oca_component_handler",
            raise_if_not_found=False,
        )
        camt_empty = self._create_type("test_camt054_in", r"^camt\.054_P.*\.xml")
        pain002 = self._create_type("test_pain002_in", r"^pain\.002-EPO_.*\.xml")
        # Any other model works here: the hook must keep it as it is.
        other_handler = self.env["ir.model"]._get("edi.exchange.type")
        camt_other = self._create_type("test_camt_other", r"^camt\.053-other.*")
        camt_other.process_model_id = other_handler
        camt_settings = self._create_type("test_camt_settings", r"^camt\.053-set.*")
        camt_settings.advanced_settings_edit = (
            "components:\n  process:\n    usage: input.process.custom\n"
        )
        if component_handler:
            pain002.process_model_id = component_handler
            camt_settings.process_model_id = component_handler
            camt_component = self._create_type("test_camt_comp", r"^camt\.054-X.*")
            camt_component.process_model_id = component_handler

        with self.assertLogs(
            "odoo.addons.account_statement_import_sftp.hooks", level="WARNING"
        ) as logs:
            set_statement_process_handler(self.env)
        self.assertIn("keep their process handler or settings", logs.output[0])

        self.assertEqual(camt_empty.process_model_id, self.handler)
        self.assertEqual(pain002.process_model_id, self.unsupported_handler)
        self.assertEqual(camt_other.process_model_id, other_handler)
        self.assertEqual(
            camt_settings.process_model_id, component_handler or self.env["ir.model"]
        )
        if component_handler:
            self.assertEqual(camt_component.process_model_id, self.handler)

    def test_migration_script(self):
        migration = load_script(
            "account_statement_import_sftp/migrations/18.0.1.0.0/post-migration.py",
            "account_statement_import_sftp_post_migration",
        )
        exchange_type = self._create_type("test_camt_migrated", r"^camt\.053-m.*")
        migration.migrate(self.env.cr, None)
        self.assertFalse(exchange_type.process_model_id)
        migration.migrate(self.env.cr, "14.0.1.0.0")
        exchange_type.invalidate_recordset()
        self.assertEqual(exchange_type.process_model_id, self.handler)

    def test_pre_init_hook_gives_xmlid_back(self):
        """Like a database where the module was uninstalled: the xmlid is gone."""
        self.env["ir.model.data"].search(
            [
                ("module", "=", "account_statement_import_sftp"),
                ("name", "=", "sftp_bank_edi"),
            ]
        ).unlink()
        self.env.registry.clear_cache()
        pre_init_hook(self.env)
        self.assertEqual(
            self.env.ref("account_statement_import_sftp.sftp_bank_edi"),
            self.backend_type,
        )
        # Loading the data file again finds the same record, no second one.
        convert_file(
            self.env,
            "account_statement_import_sftp",
            "data/edi_data.xml",
            None,
            mode="init",
        )
        self.assertEqual(
            self.env["edi.backend.type"].search([("code", "=", "bk_sftp_imp")]),
            self.backend_type,
        )
