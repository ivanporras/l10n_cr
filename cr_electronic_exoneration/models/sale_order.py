# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ==============================================================================================
    #                                    CAMPOS DE EXONERACIÓN TOTALES
    # ==============================================================================================

    total_exoneration_amount = fields.Monetary(
        string='Total Exonerado',
        compute='_compute_exoneration_totals',
        store=True,
        currency_field='currency_id',
        help='Monto total exonerado en el pedido de venta'
    )

    has_exoneration_lines = fields.Boolean(
        string='Tiene Líneas con Exoneración',
        compute='_compute_exoneration_totals',
        store=True,
        help='Indica si el pedido tiene líneas con exoneración'
    )

    # ==============================================================================================
    #                                    MÉTODOS COMPUTADOS TOTALES
    # ==============================================================================================

    @api.depends('order_line.exoneration_amount', 'order_line.has_exoneration')
    def _compute_exoneration_totals(self):
        """Calcula los totales de exoneración del pedido de venta"""
        for order in self:
            exoneration_lines = order.order_line.filtered(lambda l: l.has_exoneration)

            # 🔧 DEBUG: Ver qué valores están llegando
            _logger.info("=" * 60)
            _logger.info(f"DEBUG TOTAL EXONERACIÓN - Pedido {order.name}")
            _logger.info("=" * 60)

            total_debug = 0.0
            for line in exoneration_lines:
                _logger.info(f"Línea {line.id}: Producto={line.product_id.name}")
                _logger.info(f"  - Price Subtotal: ₡{line.price_subtotal:,.2f}")
                _logger.info(f"  - Exoneration Amount: ₡{line.exoneration_amount:,.2f}")
                _logger.info(f"  - Has Exoneration: {line.has_exoneration}")
                _logger.info(f"  - Exoneration %: {line.exoneration_percentage}%")
                total_debug += line.exoneration_amount

            _logger.info(f"TOTAL CALCULADO: ₡{total_debug:,.2f}")
            _logger.info("=" * 60)

            order.total_exoneration_amount = sum(exoneration_lines.mapped('exoneration_amount'))
            order.has_exoneration_lines = bool(exoneration_lines)

    # ==============================================================================================
    #                                  INTEGRACIÓN CON EXONERACIONES
    # ==============================================================================================

    def _get_exoneration_for_line(self, order_line):
        """
        ✅ Obtiene la exoneración aplicable para una línea de pedido
        Reutiliza la misma lógica que account.move
        """
        _logger.info("=" * 80)
        _logger.info("🔍 INICIANDO DEBUG DE EXONERACIÓN EN SALE ORDER")
        _logger.info("=" * 80)

        # 1. Verificar cliente
        _logger.info(f"👤 Cliente: {self.partner_id.name}")
        _logger.info(f"📋 Cliente ID: {self.partner_id.id}")
        _logger.info(f"✅ Tiene exoneraciones activas: {self.partner_id.has_exoneration_new}")

        if not self.partner_id.has_exoneration_new:
            _logger.error("❌ CLIENTE NO TIENE EXONERACIONES ACTIVAS")
            return False

        # 2. Verificar producto
        _logger.info(f"🛍️ Producto: {order_line.product_id.name if order_line.product_id else 'SIN PRODUCTO'}")

        if not order_line.product_id:
            _logger.error("❌ LÍNEA SIN PRODUCTO")
            return False

        # 3. Buscar código CABYS usando el mismo método que account.move.line
        cabys_code = order_line._get_product_cabys_code()

        if not cabys_code:
            _logger.error(f"❌ NO SE ENCONTRÓ CÓDIGO CABYS PARA PRODUCTO: {order_line.product_id.name}")
            return False

        _logger.info(f"✅ CÓDIGO CABYS FINAL: '{cabys_code}'")

        # 4. Buscar exoneración aplicable
        _logger.info(f"🔍 Buscando exoneración para código: '{cabys_code}'")
        exoneration = self.partner_id.get_applicable_exoneration(cabys_code)

        if exoneration:
            _logger.info(f"🎉 ¡EXONERACIÓN ENCONTRADA!")
            _logger.info(f"📄 Número: {exoneration.exoneration_number}")
            _logger.info(f"💯 Porcentaje: {exoneration.percentage_exoneration}%")
            _logger.info(f"📅 Válida hasta: {exoneration.date_expiration}")
            _logger.info(f"🏛️ Institución: {exoneration.institution_name}")
        else:
            _logger.error(f"❌ NO SE ENCONTRÓ EXONERACIÓN PARA CÓDIGO: '{cabys_code}'")

        _logger.info("=" * 80)
        return exoneration

    def _calculate_tax_with_exoneration(self, tax, base_amount, exoneration):
        """
        Calcula el impuesto aplicando la exoneración correspondiente
        Mismo método que en account.move

        Args:
            tax: Impuesto base (account.tax)
            base_amount: Monto base para cálculo
            exoneration: Exoneración aplicable

        Returns:
            dict: Diccionario con cálculos de impuesto
        """
        if not exoneration:
            # Sin exoneración, cálculo normal
            return {
                'tax_amount': base_amount * tax.amount / 100,
                'exoneration_amount': 0.0,
                'exoneration_percentage': 0.0,
                'net_tax_amount': base_amount * tax.amount / 100,
            }

        # Con exoneración
        gross_tax_amount = base_amount * tax.amount / 100
        exoneration_amount = base_amount * exoneration.percentage_exoneration / 100
        net_tax_amount = gross_tax_amount - exoneration_amount

        return {
            'tax_amount': gross_tax_amount,
            'exoneration_amount': exoneration_amount,
            'exoneration_percentage': exoneration.percentage_exoneration,
            'net_tax_amount': net_tax_amount,
            'exoneration_data': {
                'number': exoneration.exoneration_number,
                'institution': exoneration.institution_name or 'No especificada',
                'date_issue': exoneration.date_issue,
                'date_expiration': exoneration.date_expiration,
            }
        }

    # -------------------------------------------------------------------------
    # MÉTODOS DE TRANSFERENCIA A FACTURAS
    # -------------------------------------------------------------------------

    def _prepare_invoice(self):
        """
        ✅ CRÍTICO: Override para transferir datos de exoneración a la factura
        """
        invoice_vals = super()._prepare_invoice()

        # Transferir información de exoneraciones si las hay
        if self.has_exoneration_lines:
            _logger.info(f"🔄 Transfiriendo exoneraciones de pedido {self.name} a factura")
            invoice_vals.update({
                'has_exoneration_lines': self.has_exoneration_lines,
                'total_exoneration_amount': self.total_exoneration_amount,
            })

        return invoice_vals

    # -------------------------------------------------------------------------
    # MÉTODOS DE DEBUG Y UTILIDAD
    # -------------------------------------------------------------------------

    def debug_exoneration_application(self):
        """
        🔧 MÉTODO DE DEBUG: Verifica la aplicación de exoneraciones línea por línea
        """
        _logger.info("=" * 100)
        _logger.info("🧪 DEBUG COMPLETO: APLICACIÓN DE EXONERACIONES EN SALE ORDER")
        _logger.info("=" * 100)
        _logger.info(f"📄 Pedido: {self.name}")
        _logger.info(f"👤 Cliente: {self.partner_id.name}")
        _logger.info(f"🎯 Tiene exoneraciones: {self.partner_id.has_exoneration_new}")

        # Listar exoneraciones activas del cliente
        if self.partner_id.has_exoneration_new:
            active_exonerations = self.partner_id.exoneration_ids.filtered(
                lambda e: e.active and e.is_valid_today()
            )
            _logger.info(f"📋 Exoneraciones activas: {len(active_exonerations)}")

            for exo in active_exonerations:
                _logger.info(f"   📄 {exo.exoneration_number} - {exo.cabys_count} códigos CABYS")

        # Analizar cada línea
        for line in self.order_line.filtered(lambda l: l.display_type == 'line_section'):
            _logger.info(f"\n🛍️ LÍNEA: {line.product_id.name}")
            _logger.info(f"   💰 Subtotal: ₡{line.price_subtotal:,.2f}")

            cabys_code = line._get_product_cabys_code()
            _logger.info(f"   🏷️ Código CABYS: {cabys_code}")

            if cabys_code and self.partner_id.has_exoneration_new:
                exoneration = self.partner_id.get_applicable_exoneration(cabys_code)
                if exoneration:
                    has_cabys = exoneration.has_cabys_code(cabys_code)
                    _logger.info(f"   ✅ Exoneración: {exoneration.exoneration_number}")
                    _logger.info(f"   🎯 CABYS en lista: {has_cabys}")
                    _logger.info(f"   💯 Porcentaje: {exoneration.percentage_exoneration}")
                else:
                    _logger.info(f"   ❌ Sin exoneración para este código CABYS")

            _logger.info(f"   🏷️ Has exoneration: {line.has_exoneration}")
            _logger.info(f"   💸 Monto exonerado: ₡{line.exoneration_amount:,.2f}")

        _logger.info("=" * 100)