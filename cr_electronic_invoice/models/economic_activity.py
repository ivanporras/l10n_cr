from odoo import models, fields


class EconomicActivity(models.Model):
    _name = "economic.activity"
    _description = 'Economic activities listed by Ministerio de Hacienda'
    _order = "code"

    # ==============================================================================================
    #                                          ECONOMIC ACTIVITIES
    # ==============================================================================================

    active = fields.Boolean(
        default=True
    )
    code = fields.Char()
    code_old = fields.Char()
    name = fields.Char()
    description = fields.Char()

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    sale_type = fields.Selection(
        selection=[
            ('goods', 'Goods'),
            ('services', 'Services')
        ],
        default='goods',
        required=True
    )


    # _code_company_unique = models.Constraint('unique(code, company_id)', 'El código de actividad debe ser único por compañía.')
