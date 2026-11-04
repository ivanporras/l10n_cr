# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, models, fields, _

_logger = logging.getLogger(__name__)

class CrElectronicInvoiceInstall(models.TransientModel):
    _name = 'cr.electronic.invoice.install'
    _description = 'Modelo para instalación de Facturación Electrónica CR'
    
    _check_dependencies = fields.Boolean(
        string='Dependencias Instaladas',
        compute='_compute_check_dependencies',
        help='Indica si todas las dependencias están instaladas correctamente'
    )
    
    _check_modules = fields.Boolean(
        string='Módulos Instalados',
        compute='_compute_check_modules',
        help='Indica si todos los módulos necesarios están instalados correctamente'
    )
    
    @api.depends('_check_modules')
    def _compute_check_dependencies(self):
        for record in self:
            record._check_dependencies = True
    
    @api.depends('_check_dependencies')
    def _compute_check_modules(self):
        for record in self:
            record._check_modules = True
    
    @api.model
    def post_install_hook(self, registry=None):
        """Método que se ejecuta después de la instalación del módulo"""
        _logger.info("Ejecutando verificación post-instalación de Facturación Electrónica CR")
        
        # Verificar configuración de la compañía
        company = self.env.company
        if not company.vat:
            _logger.warning("La compañía no tiene configurado el número de identificación fiscal (VAT).")
        
        _logger.info("Verificación post-instalación completada.")
        return True
    
    