# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # ==============================================================================================
    #                                    CAMPOS DE EXONERACIÓN
    # ==============================================================================================

    exoneration_id = fields.Many2one(
        comodel_name='res.partner.exoneration',
        string='Exoneración Aplicada',
        compute='_compute_exoneration_data',
        store=True,
        help='Exoneración aplicada a esta línea'
    )

    exoneration_percentage = fields.Float(
        string='% Exoneración',
        compute='_compute_exoneration_data',
        store=True,
        help='Porcentaje de exoneración aplicado'
    )

    exoneration_amount = fields.Monetary(
        string='Monto Exonerado',
        compute='_compute_exoneration_data',
        store=True,
        currency_field='currency_id',
        help='Monto total exonerado en esta línea'
    )

    tax_amount_before_exoneration = fields.Monetary(
        string='IVA Bruto',
        compute='_compute_exoneration_data',
        store=True,
        currency_field='currency_id',
        help='Monto de IVA antes de aplicar exoneración'
    )

    has_exoneration = fields.Boolean(
        string='Tiene Exoneración',
        compute='_compute_exoneration_data',
        store=True,
        help='Indica si esta línea tiene exoneración aplicada'
    )

    # ==============================================================================================
    #                                    MÉTODOS COMPUTADOS CORREGIDOS
    # ==============================================================================================

    @api.depends('product_id', 'move_id.partner_id', 'price_subtotal', 'tax_ids', 'move_id.move_type')
    def _compute_exoneration_data(self):
        """✅ CORREGIDO: Calcula exoneraciones solo para productos específicos"""
        for line in self:
            # Inicializar valores por defecto
            line.exoneration_id = False
            line.exoneration_percentage = 0.0
            line.exoneration_amount = 0.0
            line.tax_amount_before_exoneration = 0.0
            line.has_exoneration = False

            # Solo procesar líneas de producto en facturas de venta
            if (line.display_type != 'product' or
                    not line.product_id or
                    not line.move_id or
                    line.move_id.move_type not in ('out_invoice', 'out_refund')):
                continue

            # Verificar si el cliente tiene exoneraciones activas
            partner = line.move_id.partner_id
            if not partner or not getattr(partner, 'has_exoneration_new', False):
                continue

            # 🔍 LOGS DE DEBUGGING DETALLADOS
            _logger.info("=" * 80)
            _logger.info("🔍 DEBUG APLICACIÓN DE EXONERACIÓN POR LÍNEA")
            _logger.info("=" * 80)
            _logger.info(f"📄 Factura: {line.move_id.name}")
            _logger.info(f"🛍️ Producto: {line.product_id.name}")
            _logger.info(f"👤 Cliente: {partner.name}")
            _logger.info(f"💰 Subtotal línea: ₡{line.price_subtotal:,.2f}")

            # Buscar código CABYS del producto
            cabys_code = line._get_product_cabys_code()
            _logger.info(f"🏷️ Código CABYS del producto: '{cabys_code}'")

            if not cabys_code:
                _logger.warning(f"⚠️ Producto sin código CABYS: {line.product_id.name}")
                continue

            # ⚠️ PUNTO CRÍTICO: Buscar exoneración específica para este código CABYS
            exoneration = partner.get_applicable_exoneration(cabys_code)

            if exoneration:
                _logger.info(f"✅ EXONERACIÓN ENCONTRADA:")
                _logger.info(f"   📋 Número: {exoneration.exoneration_number}")
                _logger.info(f"   💯 Porcentaje: {exoneration.percentage_exoneration}")
                _logger.info(f"   🏷️ Códigos CABYS: {exoneration.cabys_count}")

                # Verificar específicamente que el código CABYS esté en la lista
                has_cabys = exoneration.has_cabys_code(cabys_code)
                _logger.info(f"   🎯 Código {cabys_code} en lista: {has_cabys}")

                if has_cabys:
                    # Calcular montos con exoneración
                    tax_data = line._calculate_tax_with_exoneration(exoneration)

                    _logger.info(f"📊 CÁLCULOS DE EXONERACIÓN:")
                    _logger.info(f"   💸 IVA Bruto: ₡{tax_data['tax_amount']:,.2f}")
                    _logger.info(f"   🎁 Exoneración: ₡{tax_data['exoneration_amount']:,.2f}")
                    _logger.info(f"   💵 IVA Neto: ₡{tax_data['net_tax_amount']:,.2f}")

                    # Asignar valores calculados
                    line.exoneration_id = exoneration.id
                    line.exoneration_percentage = exoneration.percentage_exoneration * 100
                    line.exoneration_amount = tax_data['exoneration_amount']
                    line.tax_amount_before_exoneration = tax_data['tax_amount']
                    line.has_exoneration = True

                    _logger.info(f"✅ EXONERACIÓN APLICADA CORRECTAMENTE")
                else:
                    _logger.warning(f"⚠️ Código CABYS {cabys_code} NO está en lista de exoneración")
            else:
                _logger.info(f"ℹ️ No hay exoneración para código CABYS: {cabys_code}")

            _logger.info("=" * 80)

    def _get_product_cabys_code(self):
        """Obtiene el código CABYS del producto"""
        if not self.product_id:
            return False

        # Método 1: Código directo del producto
        if hasattr(self.product_id, 'cabys_code') and self.product_id.cabys_code:
            return self.product_id.cabys_code

        # Método 2: Desde relación con catálogo CABYS
        if hasattr(self.product_id, 'cabys_product_id') and self.product_id.cabys_product_id:
            return self.product_id.cabys_product_id.codigo

        # Método 3: Desde categoría del producto
        if (self.product_id.categ_id and
                hasattr(self.product_id.categ_id, 'cabys_code') and
                self.product_id.categ_id.cabys_code):
            return self.product_id.categ_id.cabys_code

        return False

    def _calculate_tax_with_exoneration(self, exoneration):
        """
        🔧 MÉTODO CORREGIDO: Calcula los impuestos aplicando la exoneración como reducción del porcentaje
        """
        if not exoneration or not self.tax_ids:
            return {
                'tax_amount': 0.0,
                'exoneration_amount': 0.0,
                'net_tax_amount': 0.0,
            }

        # Calcular IVA con exoneración aplicada al porcentaje
        total_tax_amount = 0.0
        total_exoneration_amount = 0.0

        for tax in self.tax_ids:
            # ✅ LÓGICA CORREGIDA: Restar porcentaje de exoneración del porcentaje de IVA

            # Convertir porcentaje de exoneración a formato decimal si es necesario
            exoneration_percentage = exoneration.percentage_exoneration
            if exoneration_percentage > 1:
                exoneration_percentage = exoneration_percentage / 100

            # Calcular IVA bruto (antes de exoneración)
            gross_tax_rate = tax.amount / 100  # 13% -> 0.13
            gross_tax_amount = self.price_subtotal * gross_tax_rate
            total_tax_amount += gross_tax_amount

            # Calcular exoneración sobre el IVA
            if gross_tax_rate > 0:
                # Exoneración como reducción del porcentaje de IVA
                exoneration_rate = min(exoneration_percentage, gross_tax_rate)  # No puede ser mayor al IVA
                exoneration_amount = self.price_subtotal * exoneration_rate
                total_exoneration_amount += exoneration_amount

        return {
            'tax_amount': total_tax_amount,
            'exoneration_amount': total_exoneration_amount,
            'net_tax_amount': max(0.0, total_tax_amount - total_exoneration_amount),
        }

    # ==============================================================================================
    #                                    🔧 NUEVO: OVERRIDE DE CÁLCULO DE IMPUESTOS
    # ==============================================================================================

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_totals(self):
        """
        Override del método de cálculo de totales para aplicar exoneraciones
        """
        # Llamar al método original primero
        super()._compute_totals()

        # Luego aplicar exoneraciones
        for line in self:
            if (line.has_exoneration and line.exoneration_amount > 0 and
                    line.display_type == 'product'):
                # Reducir el price_total por la exoneración
                line.price_total = line.price_subtotal + (line.tax_amount_before_exoneration - line.exoneration_amount)

                _logger.info(
                    f'Línea {line.id}: Subtotal={line.price_subtotal}, IVA Original={line.tax_amount_before_exoneration}, Exonerado={line.exoneration_amount}, Total Final={line.price_total}')