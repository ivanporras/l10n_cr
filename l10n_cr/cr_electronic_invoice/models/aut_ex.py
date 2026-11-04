# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Modelo para Tipos de Documento de Exoneración o Autorización
# Según Nota 10.1 de la Resolución DGT - Versión 4.4

from odoo import models, fields, api


class AutEx(models.Model):
    _name = "aut.ex"
    _description = 'Tipo de Documento de Exoneración o Autorización'
    _rec_names_search = ['code', 'name']

    # ==============================================================================================
    #                                    EXONERATION TYPES (Nota 10.1)
    # ==============================================================================================
    #
    # Códigos según Nota 10.1 - Versión 4.4 (Rige a partir del 01/06/2025)
    #
    # | Código | Descripción                                                                 |
    # |--------|-----------------------------------------------------------------------------|
    # |   01   | Compras autorizadas por la DGT (INHABILITADO - solo NC/ND)                  |
    # |   02   | Ventas exentas a diplomáticos                                               |
    # |   03   | Autorizado por Ley especial                                                 |
    # |   04   | Exenciones DGH Autorización Local Genérica                                  |
    # |   05   | Exenciones DGH Transitorio V (INHABILITADO - solo NC/ND)                    |
    # |   06   | Servicios turísticos inscritos ante ICT (INHABILITADO - solo NC/ND)         |
    # |   07   | Transitorio XVII (INHABILITADO - solo NC/ND)                                |
    # |   08   | Exoneración a Zona Franca (NUEVO v4.4)                                      |
    # |   09   | Exoneración servicios complementarios exportación art.11 RLIVA (NUEVO v4.4) |
    # |   10   | Órgano de las corporaciones municipales (NUEVO v4.4)                        |
    # |   11   | Exenciones DGH Autorización Impuesto Local Concreta (NUEVO v4.4)           |
    # |   99   | Otros                                                                       |
    #
    # ==============================================================================================

    active = fields.Boolean(
        default=True,
        string='Activo'
    )
    code = fields.Char(
        string='Código',
        required=True,
        size=2,
        index=True,
        help='Código de 2 dígitos según Nota 10.1 de la Resolución DGT v4.4'
    )
    name = fields.Char(
        string='Descripción',
        required=True,
        translate=True,
        help='Descripción del tipo de documento de exoneración o autorización'
    )
    
    # Campo computado para identificar si requiere artículo de ley
    requires_article = fields.Boolean(
        string='Requiere Artículo',
        compute='_compute_requires_article',
        store=False,
        help='Indica si este tipo de documento requiere número de artículo de ley. '
             'Obligatorio para códigos 02, 03, 06, 07 y 08 según Nota 10.1.'
    )
    
    # Campo para indicar si está inhabilitado
    is_disabled = fields.Boolean(
        string='Inhabilitado',
        default=False,
        help='Indica si este código está inhabilitado para uso general. '
             'Solo puede usarse en Notas de Crédito y Débito.'
    )
    
    # Notas adicionales sobre el uso
    notes = fields.Text(
        string='Notas',
        translate=True,
        help='Notas explicativas sobre el uso de este tipo de documento'
    )

    _code_uniq = models.Constraint('UNIQUE(code)', 'El código de tipo de exoneración debe ser único.')

    @api.depends('code')
    def _compute_requires_article(self):
        """
        Los códigos 02, 03, 06, 07 y 08 requieren número de artículo según Nota 10.1.
        - 02: Ventas exentas a diplomáticos
        - 03: Autorizado por Ley especial
        - 06: Servicios turísticos inscritos ante ICT (inhabilitado)
        - 07: Transitorio XVII (inhabilitado)
        - 08: Exoneración a Zona Franca
        """
        codes_requiring_article = ('02', '03', '06', '07', '08')
        for record in self:
            record.requires_article = record.code in codes_requiring_article

    @api.depends('code', 'name', 'is_disabled')
    def _compute_display_name(self):
        """Mostrar código y descripción en el selector"""
        for record in self:
            name = f"[{record.code}] {record.name}"
            if record.is_disabled:
                name = f"{name} (Inhabilitado)"
            record.display_name = name
