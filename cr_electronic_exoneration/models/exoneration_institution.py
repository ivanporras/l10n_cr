from odoo import models, fields, api


class ExonerationInstitution(models.Model):
    _name = 'exoneration.institution'
    _description = 'Instituciones Emisoras de Exoneraciones'
    _order = 'name'

    name = fields.Char(
        string='Nombre de la Institución',
        required=True
    )
    code = fields.Char(
        string='Código Oficial',
        help='Código oficial usado en documentos de Hacienda'
    )
    active = fields.Boolean(
        string='Activa',
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
        inverse_name='institution_id',
        string='Exoneraciones'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El código de institución debe ser único'),
    ]

    # CORRECCIÓN: Mejorar método compute
    @api.depends('exoneration_ids', 'exoneration_ids.active')
    def _compute_exoneration_count(self):
        for institution in self:
            if institution.exoneration_ids:
                institution.exoneration_count = len(institution.exoneration_ids)
            else:
                institution.exoneration_count = 0

    def action_view_exonerations(self):
        """Ver todas las exoneraciones de esta institución"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Exoneraciones - {self.name}',
            'res_model': 'res.partner.exoneration',
            'view_mode': 'tree,form',
            'domain': [('institution_id', '=', self.id)],
            'context': {'default_institution_id': self.id},
            'target': 'current',
        }