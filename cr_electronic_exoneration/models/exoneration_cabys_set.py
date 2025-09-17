from odoo import models, fields, api


class ExonerationCabysSet(models.Model):
    _name = 'exoneration.cabys.set'
    _description = 'Conjunto de Códigos CABYS por Exoneración'
    _rec_name = 'display_name'

    exoneration_number = fields.Char(
        string='Número de Exoneración',
        required=True
    )

    cabys_line_ids = fields.One2many(
        comodel_name='exoneration.cabys.line',
        inverse_name='cabys_set_id',
        string='Códigos CABYS'
    )

    cabys_count = fields.Integer(
        string='Cantidad de Códigos',
        compute='_compute_cabys_count'
    )

    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('cabys_line_ids')
    def _compute_cabys_count(self):
        for record in self:
            record.cabys_count = len(record.cabys_line_ids)

    @api.depends('cabys_count', 'exoneration_number')
    def _compute_display_name(self):
        for record in self:
            if record.cabys_count:
                record.display_name = f"{record.cabys_count} registros"
            else:
                record.display_name = "Sin códigos"