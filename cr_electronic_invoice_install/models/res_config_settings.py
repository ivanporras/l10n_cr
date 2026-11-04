# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_cr_electronic_invoice = fields.Boolean(
        string='Facturación Electrónica CR',
        help='Instala el módulo de facturación electrónica de Costa Rica.'
    )
    
    module_cabys = fields.Boolean(
        string='Catálogo de Bienes y Servicios (CABYS)',
        help='Instala el catálogo de bienes y servicios requerido por el Ministerio de Hacienda.'
    )
    
    module_cr_import_vendor_bills = fields.Boolean(
        string='Importación de Facturas de Proveedores',
        help='Permite importar facturas electrónicas de proveedores.'
    )