# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

from odoo import models
from odoo.exceptions import UserError


class CamtParser(models.AbstractModel):
    """Parser for camt bank statement import files."""

    _inherit = "account.statement.import.camt.parser"

    def _get_partner_ref(self, isr):
        ICP = self.env["ir.config_parameter"]
        ref_format = ICP.sudo().get_param("qrr_partner_ref")
        if not ref_format:
            return
        config = ref_format.split(",")
        if len(config) == 2:
            start, size = config
        elif len(config) == 1:
            start = config[0]
            size = 6
        else:
            raise UserError(
                self.env._(
                    "Config parameter `qrr_partner_ref` is wrong.\n"
                    "It must be in format `i[,n]` \n"
                    "where `i` is the position of the first digit and\n"
                    "`n` the number of digit in the reference,"
                    " by default 6.\n"
                    'e.g. "13,6"'
                )
            )
        try:
            start = int(start) - 1  # count from 1 instead of 0
            size = int(size)
            end = start + size
        except ValueError:
            raise UserError(
                self.env._(
                    "Config parameter `qrr_partner_ref` is wrong.\n"
                    "It must be in format `i[,n]` \n"
                    "`i` and `n` must be integers.\n"
                    'e.g. "13,6"'
                )
            ) from None
        return isr[start:end].lstrip("0")

    def parse_transaction_details(self, ns, node, transaction):
        """Put the additional remittance information in the label (the QRR
        when there is none) and the QRR in the reference. Without QRR, use
        the other available information for the label.
        """
        super().parse_transaction_details(ns, node, transaction)

        qrr_number = node.xpath(
            "./ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref", namespaces={"ns": ns}
        )
        if len(qrr_number):
            addtl_rmt_inf = [
                info.text
                for info in node.xpath(
                    "./ns:RmtInf/ns:Strd/ns:AddtlRmtInf", namespaces={"ns": ns}
                )
                if info.text
            ]
            transaction["payment_ref"] = " ".join(addtl_rmt_inf) or qrr_number[0].text
            partner_ref = self._get_partner_ref(qrr_number[0].text)
            if partner_ref:
                transaction["partner_ref"] = partner_ref
        else:
            xpath_exprs = [
                "./ns:RmtInf/ns:Ustrd|./ns:RtrInf/ns:AddtlInf",
                "./ns:AddtlNtryInf",
                "/ns:Refs/ns:InstrId",
            ]
            payment_ref = transaction["payment_ref"]
            for xpath_expr in xpath_exprs:
                found_node = node.xpath(xpath_expr, namespaces={"ns": ns})
                if found_node:
                    payment_ref = found_node[0].text
                    break
            trans_id_node = (
                node.getparent()
                .getparent()
                .xpath("./ns:AcctSvcrRef", namespaces={"ns": ns})
            )
            if trans_id_node:
                payment_ref = f"{payment_ref} ({trans_id_node[0].text})"
            if payment_ref:
                transaction["payment_ref"] = payment_ref

        # QRR in ref, transaction id otherwise
        self.add_value_from_node(
            ns,
            node,
            [
                "./ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref",
                "./../../ns:AcctSvcrRef",
                "./ns:Refs/ns:EndToEndId",
            ],
            transaction,
            "ref",
        )
        return True

    def parse_statement(self, ns, node):
        """In case of a camt.054 file, the QR-IBAN to be used as the
        account_number is found in the entry's own reference rather than
        the account-level IBAN."""
        result = super().parse_statement(ns, node)
        re_camt_version = re.compile(
            r"(^urn:iso:std:iso:20022:tech:xsd:camt.054." r"|^ISO:camt.054.)"
        )
        if re_camt_version.search(ns):
            self.add_value_from_node(
                ns,
                node,
                [
                    "./ns:Ntry[1]/ns:NtryRef",
                    "./ns:Acct/ns:Id/ns:IBAN",
                    "./ns:Acct/ns:Id/ns:Othr/ns:Id",
                ],
                result,
                "account_number",
            )
        return result
