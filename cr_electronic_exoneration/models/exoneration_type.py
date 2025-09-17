from odoo import models, fields, api


class ExonerationType(models.Model):
    _name = 'exoneration.type'
    _description = 'Tipos de Exoneración'
    _order = 'name'

    name = fields.Char(
        string='Nombre del Tipo',
        required=True
    )
    code = fields.Char(
        string='Código para Hacienda',
        help='Código usado en documentos electrónicos'
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    description = fields.Text(
        string='Descripción'
    )

    # Estadísticas - CORRECCIÓN: Agregar store=True
    exoneration_count = fields.Integer(
        string='Cantidad de Exoneraciones',
        compute='_compute_exoneration_count',
        store=True  # ✅ AGREGADO
    )

    exoneration_ids = fields.One2many(
        comodel_name='res.partner.exoneration',
        inverse_name='exoneration_type_id',
        string='Exoneraciones'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El código de tipo debe ser único'),
    ]

    # CORRECCIÓN: Mejorar método compute
    @api.depends('exoneration_ids', 'exoneration_ids.active')
    def _compute_exoneration_count(self):
        for ex_type in self:
            if ex_type.exoneration_ids:
                ex_type.exoneration_count = len(ex_type.exoneration_ids)
            else:
                ex_type.exoneration_count = 0

    def action_view_exonerations(self):
        """Ver todas las exoneraciones de este tipo"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Exoneraciones - {self.name}',
            'res_model': 'res.partner.exoneration',
            'view_mode': 'tree,form',
            'domain': [('exoneration_type_id', '=', self.id)],
            'context': {'default_exoneration_type_id': self.id},
            'target': 'current',
        }