# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def compute_all(self, price_unit, currency=None, quantity=1.0, product=None, partner=None, is_refund=False,
                    handle_price_include=True, include_caba_tags=False, fixed_multiplicator=1):
        """
        🔧 OVERRIDE CORREGIDO: Aplicar exoneraciones como reducción del porcentaje de IVA
        """
        # Llamar al método original
        result = super().compute_all(
            price_unit, currency, quantity, product, partner,
            is_refund, handle_price_include, include_caba_tags, fixed_multiplicator
        )

        # Aplicar exoneraciones si corresponde
        if (partner and product and
                hasattr(partner, 'has_exoneration_new') and
                partner.has_exoneration_new):

            # Obtener código CABYS del producto
            cabys_code = self._get_product_cabys_code(product)
            if cabys_code:
                # Buscar exoneración aplicable
                exoneration = partner.get_applicable_exoneration(cabys_code)
                if exoneration:
                    _logger.info(
                        f'Aplicando exoneración: {exoneration.exoneration_number} - {exoneration.percentage_exoneration}%')

                    # Convertir porcentaje si es necesario
                    exoneration_percentage = exoneration.percentage_exoneration
                    if exoneration_percentage > 1:
                        exoneration_percentage = exoneration_percentage / 100

                    # Aplicar exoneración a cada impuesto
                    for tax_data in result.get('taxes', []):
                        tax = self.browse(tax_data['id'])
                        original_amount = tax_data['amount']

                        if tax.amount > 0:
                            # ✅ LÓGICA CORREGIDA: Reducir porcentaje de IVA por exoneración
                            tax_rate = tax.amount / 100  # 13% -> 0.13
                            exoneration_rate = min(exoneration_percentage, tax_rate)  # Máximo el IVA
                            effective_tax_rate = tax_rate - exoneration_rate  # 0.13 - 0.12 = 0.01

                            # Recalcular impuesto con tasa efectiva
                            base_amount = result.get('total_excluded', 0)
                            new_tax_amount = base_amount * effective_tax_rate
                            tax_data['amount'] = new_tax_amount

                            _logger.info(
                                f'Impuesto {tax.name}: Tasa original {tax_rate * 100}%, '
                                f'Exoneración {exoneration_rate * 100}%, '
                                f'Tasa efectiva {effective_tax_rate * 100}%, '
                                f'Monto: ₡{new_tax_amount:,.2f}')

                    # Recalcular total_included
                    if 'total_excluded' in result:
                        result['total_included'] = result['total_excluded'] + sum(
                            t['amount'] for t in result.get('taxes', []))

        return result

    def _get_product_cabys_code(self, product):
        """Obtiene el código CABYS del producto"""
        if not product:
            return False

        # Método 1: Código directo del producto
        if hasattr(product, 'cabys_code') and product.cabys_code:
            return product.cabys_code

        # Método 2: Desde relación con catálogo CABYS
        if hasattr(product, 'cabys_product_id') and product.cabys_product_id:
            return product.cabys_product_id.codigo

        # Método 3: Desde categoría del producto
        if (product.categ_id and
                hasattr(product.categ_id, 'cabys_code') and
                product.categ_id.cabys_code):
            return product.categ_id.cabys_code

        return False