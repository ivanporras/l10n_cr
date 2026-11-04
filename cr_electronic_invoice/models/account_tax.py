# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
#
# Extensión del modelo account.tax para facturación electrónica Costa Rica
# Compatible con versión 4.4 de la Resolución DGT

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class IvaCodeType(models.Model):
    _description = 'Account Tax Electronic'
    _inherit = "account.tax"

    # ==============================================================================================
    #                                          TAXES
    # ==============================================================================================
    #
    # Códigos de Impuesto según Nota 8 - Versión 4.4:
    #
    # | Código | Descripción                                    |
    # |--------|------------------------------------------------|
    # |   01   | Impuesto General sobre las Ventas              |
    # |   02   | Impuesto Selectivo de Consumo                  |
    # |   03   | Impuesto Único a los Combustibles              |
    # |   04   | Impuesto Específico a las Bebidas Alcohólicas  |
    # |   05   | Impuesto Específico a las Bebidas No Alcohólicas|
    # |   06   | Impuesto Específico al Jabón de Tocador        |
    # |   07   | IVA cálculo especial                           |
    # |   08   | Impuesto al Cemento                            |
    # |   12   | Impuesto Específico al Cemento                 |
    # |   99   | Otros                                          |
    #
    # Tarifas de IVA según Nota 8.1 - Versión 4.4:
    #
    # | Código | Descripción                                    |
    # |--------|------------------------------------------------|
    # |   01   | Tarifa 0% (Artículo 32, num 1, RLIVA)          |
    # |   02   | Tarifa reducida 1%                             |
    # |   03   | Tarifa reducida 2%                             |
    # |   04   | Tarifa reducida 4%                             |
    # |   05   | Transitorio 0%                                 |
    # |   06   | Transitorio 4%                                 |
    # |   07   | Transitorio 8% (INHABILITADO)                  |
    # |   08   | Tarifa general 13%                             |
    # |   09   | Tarifa reducida 0.5%                           |
    # |   10   | Tarifa Exenta                                  |
    # |   11   | Tarifa 0% sin derecho a crédito                |
    #
    # ==============================================================================================

    # --- Código de Impuesto (Nota 8) ---
    tax_code = fields.Char(
        string="Código de Impuesto",
        size=2,
        help="Código de impuesto según Nota 8 de la Resolución DGT. "
             "Ejemplos: 01 (IVA), 02 (Selectivo Consumo), 03 (Combustibles), etc."
    )
    
    # --- Descripción de Tarifa IVA ---
    iva_tax_desc = fields.Char(
        string="Descripción Tarifa IVA",
        default='N/A',
        help="Descripción de la tarifa del IVA según Nota 8.1"
    )
    
    # --- Código de Tarifa IVA (Nota 8.1) ---
    iva_tax_code = fields.Char(
        string="Código Tarifa IVA",
        size=2,
        default='N/A',
        help="Código de tarifa del IVA según Nota 8.1. "
             "Ejemplos: 01 (0%), 08 (13%), 09 (0.5%), etc."
    )

    # --- Campos para Exoneración ---
    has_exoneration = fields.Boolean(
        string="Tiene Exoneración",
        default=False,
        help="Indica si este impuesto tiene una exoneración configurada"
    )

    percentage_exoneration = fields.Float(
        string="Tarifa Exonerada",
        digits=(4, 2),
        help="Porcentaje de exoneración a aplicar sobre el impuesto base"
    )

    tax_root = fields.Many2one(
        comodel_name='account.tax',
        string="Impuesto Base",
        help="Impuesto base sobre el cual se aplica la exoneración"
    )

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.onchange('percentage_exoneration')
    def _onchange_percentage_exoneration(self):
        self.tax_compute_exoneration()

    @api.onchange('tax_root')
    def _onchange_tax_root(self):
        self.tax_compute_exoneration()

    def tax_compute_exoneration(self):
        if self.percentage_exoneration <= 13:
            if self.tax_root:
                self.amount = self.tax_root.amount - self.percentage_exoneration
        else:
            raise UserError(_('El porcentaje no puede ser mayor a 13'))

    # ==============================================================================================
    #                          COMPUTE METHODS
    # ==============================================================================================

    def tax_compute_exoneration(self):
        """
        Calcular el monto del impuesto con exoneración.
        
        El monto se calcula como:
        monto = impuesto_base - tarifa_exonerada
        
        La tarifa exonerada no puede ser mayor al impuesto base.
        """
        for record in self:
            if record.has_exoneration and record.tax_root:
                base_amount = record.tax_root.amount
                
                # Validar que la tarifa exonerada no sea mayor al impuesto base
                if record.percentage_exoneration > base_amount:
                    raise UserError(_(
                        'La tarifa exonerada (%s) no puede ser mayor al impuesto base (%s).'
                    ) % (record.percentage_exoneration, base_amount))
                
                # Calcular el nuevo monto
                record.amount = base_amount - record.percentage_exoneration
            elif not record.has_exoneration:
                # Si no tiene exoneración, el monto se mantiene
                pass

    def _compute_amount(self, base_amount, price_unit, quantity=1.0, product=None, partner=None, fixed_multiplicator=100):
            """
            Override para considerar la exoneración del cliente.
            
            Si el cliente (partner) tiene exoneración configurada:
            - has_exoneration = True
            - percentage_exoneration = porcentaje de exoneración (ej: 13)
            
            El impuesto se reducirá proporcionalmente en el asiento contable.
            
            Ejemplo:
            - Base: 50,000
            - IVA: 13%
            - Impuesto completo: 6,500
            - Exoneración: 13%
            - Impuesto neto: 0
            """
            # Obtener el cálculo estándar
            result = super()._compute_amount(base_amount, price_unit, quantity, product, partner, fixed_multiplicator)
            
            # Validar CABYS antes de aplicar reducción por exoneración
            if partner and product:
                has_exoneration = hasattr(partner, 'has_exoneration') and partner.has_exoneration
                percentage_exoneration = hasattr(partner, 'percentage_exoneration') and partner.percentage_exoneration or 0
                
                if has_exoneration and percentage_exoneration > 0:
                    # --- VALIDACIÓN DE CABYS ---
                    allowed_codes = [code.name for code in partner.allowed_cabys_ids]
                    cabys_code = product.cabys_code or (product.categ_id and product.categ_id.cabys_code)
                    
                    # Si el partner tiene lista restrictiva y el producto NO está en ella, NO exonerar
                    if allowed_codes and cabys_code and cabys_code not in allowed_codes:
                        return result
                    # ---------------------------

                    tax_rate = self.amount
                    if tax_rate > 0:
                        exoneration_ratio = min(percentage_exoneration / tax_rate, 1.0)
                        result = result * (1 - exoneration_ratio)
            
            return result

    # ==============================================================================================
    #                          CONSTRAINT METHODS
    # ==============================================================================================

    @api.constrains('has_exoneration', 'tax_root', 'percentage_exoneration')
    def _check_exoneration_config(self):
        """Validar configuración de exoneración"""
        for record in self:
            if record.has_exoneration:
                # Debe tener impuesto base
                if not record.tax_root:
                    raise ValidationError(_(
                        'Si el impuesto tiene exoneración, debe especificar el impuesto base.'
                    ))
                
                # La tarifa exonerada debe ser mayor a 0
                if record.percentage_exoneration <= 0:
                    raise ValidationError(_(
                        'Si el impuesto tiene exoneración, la tarifa exonerada debe ser mayor a 0.'
                    ))
                
                # La tarifa exonerada no puede ser mayor al impuesto base
                if record.percentage_exoneration > record.tax_root.amount:
                    raise ValidationError(_(
                        'La tarifa exonerada (%.2f%%) no puede ser mayor al impuesto base (%.2f%%).'
                    ) % (record.percentage_exoneration, record.tax_root.amount))

    @api.constrains('tax_root')
    def _check_tax_root_not_exoneration(self):
        """El impuesto base no puede ser otro impuesto con exoneración"""
        for record in self:
            if record.tax_root and record.tax_root.has_exoneration:
                raise ValidationError(_(
                    'El impuesto base no puede ser otro impuesto con exoneración.'
                ))

    # ==============================================================================================
    #                          HELPER METHODS
    # ==============================================================================================

    def get_tax_data_for_xml(self):
        """
        Retornar datos del impuesto formateados para generación de XML.
        
        Returns:
            dict: Datos del impuesto
        """
        self.ensure_one()
        
        data = {
            'tax_code': self.tax_code or '',
            'tarifa': self.amount,
            'iva_tax_desc': self.iva_tax_desc or 'N/A',
            'iva_tax_code': self.iva_tax_code or 'N/A',
        }
        
        if self.has_exoneration:
            data.update({
                'has_exoneration': True,
                'exoneration_percentage': self.percentage_exoneration,
                'tax_root_code': self.tax_root.tax_code if self.tax_root else '',
                'tax_root_amount': self.tax_root.amount if self.tax_root else 0,
            })
        else:
            data['has_exoneration'] = False
        
        return data
