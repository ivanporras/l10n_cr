# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, _, fields
from odoo.exceptions import UserError


class CrMultipleInvoiceValidation(models.TransientModel):
    _name = 'cr.multiple.invoice.validation'
    _description = 'Multiple invoice validation Wizard'

    iva_condition = fields.Selection([
        ('gecr', 'Generate IVA credit'),
        ('crpa', 'Generates partial IVA credit'),
        ('bica', 'Capital assets'),
        ('gcnc', 'Current spending does not generate credit'),
        ('prop', 'Proportionality')],
        string='IVA Condition',
        required=False,
        default='gecr',
    )

    state_invoice_partner = fields.Selection(
        [('1', 'Accepted'),
         ('2', 'Partial acceptance'),
         ('3', 'Rejected')],
        'Customer response')

    invoice_ids = fields.Many2many('account.move', string='Invoices')

    alert_warning = fields.Html(string='Alert warning')

    import_bill_account_id = fields.Many2one('account.account', string='Expense Account',
                                             domain=[('deprecated', '=', False)],
                                             help='Assign a spending account to each line')
    import_bill_account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account',
                                                      help='Assign an analytical account to each line')

    @api.model
    def default_get(self, fields_list):
        res = super(CrMultipleInvoiceValidation, self).default_get(fields_list)
        active_ids = self._context.get('active_ids')
        if active_ids:
            invoices = self.env['account.move'].browse(active_ids)
            valid_invoices = invoices.filtered(lambda i: i.state == 'draft' and i.move_type == 'in_invoice')
            res['invoice_ids'] = [(6, 0, valid_invoices.ids)]
            
            invalid_names = (invoices - valid_invoices).mapped('name')
            if invalid_names:
                res['alert_warning'] = _("<div class='alert alert-danger' role='alert'> Some records were removed because they are not in draft or are not vendor bills: %s </div>") % " - ".join(invalid_names)
        return res

    def run_validate(self):
        self.ensure_one()
        for inv in self.invoice_ids:
            inv.iva_condition = self.iva_condition
            inv.state_invoice_partner = self.state_invoice_partner
            for rec in inv.invoice_line_ids:
                if self.import_bill_account_id:
                    rec.account_id = self.import_bill_account_id
                if self.import_bill_account_analytic_id:
                    rec.analytic_distribution = {str(self.import_bill_account_analytic_id.id): 100}
            inv.action_post()
        return {'type': 'ir.actions.act_window_close'}
