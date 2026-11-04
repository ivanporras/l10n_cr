# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Modelo para Instituciones que emiten Exoneraciones
# Según Nota 23 de la Resolución DGT - Versión 4.4

from odoo import models, fields, api


class InstitutionExoneration(models.Model):
    _name = "institution.exoneration"
    _description = 'Institución que Emite Exoneración (Nota 23)'
    _rec_names_search = ['code', 'name']

    # ==============================================================================================
    #                          INSTITUTIONS (Nota 23 - Versión 4.4)
    # ==============================================================================================
    #
    # Códigos según Nota 23 - Versión 4.4
    #
    # | Código | Nombre de la Institución                                        |
    # |--------|-----------------------------------------------------------------|
    # |   01   | Ministerio de Hacienda                                          |
    # |   02   | Ministerio de Relaciones Exteriores y Culto                     |
    # |   03   | Ministerio de Agricultura y Ganadería                           |
    # |   04   | Ministerio de Economía, Industria y Comercio                    |
    # |   05   | Cruz Roja Costarricense                                         |
    # |   06   | Benemérito Cuerpo de Bomberos de Costa Rica                     |
    # |   07   | Asociación Obras del Espíritu Santo                             |
    # |   08   | Federación Cruzada Nacional de protección al Anciano (Fecrunapa)|
    # |   09   | Escuela de Agricultura de la Región Húmeda (EARTH)              |
    # |   10   | Instituto Centroamericano de Administración de Empresas (INCAE) |
    # |   11   | Junta de Protección Social (JPS)                                |
    # |   12   | Autoridad Reguladora de los Servicios Públicos (Aresep)         |
    # |   99   | Otros                                                           |
    #
    # ==============================================================================================

    code = fields.Char(
        string='Código',
        required=True,
        size=2,
        index=True,
        help='Código de 2 dígitos según Nota 23 de la Resolución DGT v4.4'
    )
    name = fields.Char(
        string='Nombre de la Institución',
        required=True,
        translate=True,
        help='Nombre de la institución o dependencia que emite la exoneración'
    )
    active = fields.Boolean(
        default=True,
        string='Activo'
    )
    
    # Campo computado para identificar si es "Otros"
    is_other = fields.Boolean(
        string='Es Otros',
        compute='_compute_is_other',
        store=False,
        help='Indica si este código representa "Otros" y requiere descripción adicional'
    )

    _code_uniq = models.Constraint('UNIQUE(code)', 'El código de institución debe ser único.')

    @api.depends('code')
    def _compute_is_other(self):
        """El código 99 representa 'Otros' y requiere campo adicional"""
        for record in self:
            record.is_other = record.code == '99'

    @api.depends('code', 'name')
    def _compute_display_name(self):
        """Mostrar código y nombre en el selector"""
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"
