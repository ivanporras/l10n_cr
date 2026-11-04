# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AccountMoveOtroTextoConfirm(models.TransientModel):
    _name = "account.move.otro.texto.confirm"
    _description = "Confirmación para campos vacíos en reglas de OtroTexto"

    move_id = fields.Many2one("account.move", readonly=True, required=True)
    warning_message = fields.Html(readonly=True)

    def action_confirm_and_post(self):
        """
        Proceeds with the invoice posting after user confirmation, bypassing
        the empty field validation for 'OtroTexto' rules.
        """
        self.ensure_one()
        return self.move_id.with_context(otro_texto_bypass_validation=True).action_post()