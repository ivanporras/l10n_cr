from odoo import fields, models, api


class PosPaymentMethod(models.Model):
    _description = 'PosPaymentMethod'
    _inherit = "pos.payment.method"

    account_payment_method_id = fields.Many2one('payment.methods', string="Accounting Payment Method")
