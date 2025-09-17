from odoo import models, fields


class ExonerationCabysLine(models.Model):
    _name = 'exoneration.cabys.line'
    _description = 'Línea de Código CABYS'
    _order = 'cabys_code'

    cabys_set_id = fields.Many2one(
        comodel_name='exoneration.cabys.set',
        string='Conjunto',
        required=True,
        ondelete='cascade'
    )

    cabys_code = fields.Char(
        string='Código CABYS',
        required=True
    )

    description = fields.Char(
        string='Descripción'
    )

    _sql_constraints = [
        ('cabys_code_set_unique',
         'unique(cabys_set_id, cabys_code)',
         'El código CABYS debe ser único por conjunto'),
    ]