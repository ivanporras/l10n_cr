# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Modelo para líneas de códigos CABYS autorizados en exoneraciones

from odoo import models, fields, api


class ResPartnerCabysLine(models.Model):
    _name = "res.partner.cabys.line"
    _description = 'Códigos CABYS Autorizados para Exoneración'

    # ==============================================================================================
    #                          CABYS CODES FOR EXONERATION
    # ==============================================================================================
    #
    # Este modelo almacena los códigos CABYS autorizados para un cliente con exoneración.
    # Cuando se aplica una exoneración, el código CABYS indicado por el emisor debe
    # encontrarse en la autorización emitida por la Dirección General de Hacienda.
    # Caso contrario Hacienda rechazará el comprobante.
    #
    # ==============================================================================================

    name = fields.Char(
        string='Código CABYS',
        required=True,
        size=13,
        help='Código CABYS de 13 dígitos autorizado para exoneración'
    )
    
    parent_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        ondelete='cascade',
        index=True
    )
    
    # Campo opcional para descripción del código CABYS
    description = fields.Char(
        string='Descripción',
        help='Descripción opcional del código CABYS'
    )
    
    # Relación con el modelo cabys.producto si existe
    cabys_id = fields.Many2one(
        comodel_name='cabys.producto',
        string='CABYS',
        compute='_compute_cabys_id',
        store=False,
        help='Referencia al código CABYS en el catálogo'
    )

    def _compute_cabys_id(self):
        """Buscar el código CABYS en el catálogo"""
        for record in self:
            if record.name:
                cabys = self.env['cabys.producto'].search(
                    [('codigo', '=', record.name)],
                    limit=1
                )
                record.cabys_id = cabys.id if cabys else False
            else:
                record.cabys_id = False

    @api.depends('name', 'description')
    def _compute_display_name(self):
        for record in self:
            if record.description:
                record.display_name = f"{record.name} - {record.description}"
            else:
                record.display_name = record.name
