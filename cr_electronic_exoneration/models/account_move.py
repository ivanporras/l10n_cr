from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ==============================================================================================
    #                                    CAMPOS DE EXONERACIÓN TOTALES
    # ==============================================================================================

    total_exoneration_amount = fields.Monetary(
        string='Total Exonerado',
        compute='_compute_exoneration_totals',
        store=True,
        currency_field='currency_id',
        help='Monto total exonerado en la factura'
    )

    has_exoneration_lines = fields.Boolean(
        string='Tiene Líneas con Exoneración',
        compute='_compute_exoneration_totals',
        store=True,
        help='Indica si la factura tiene líneas con exoneración'
    )

    # ==============================================================================================
    #                                    MÉTODOS COMPUTADOS TOTALES
    # ==============================================================================================

    @api.depends('invoice_line_ids.exoneration_amount', 'invoice_line_ids.has_exoneration')
    def _compute_exoneration_totals(self):
        """Calcula los totales de exoneración de la factura"""
        for move in self:
            exoneration_lines = move.invoice_line_ids.filtered(lambda l: l.has_exoneration)

            # 🔧 DEBUG: Ver qué valores están llegando
            _logger.info("=" * 60)
            _logger.info(f"DEBUG TOTAL EXONERACIÓN - Factura {move.name}")
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

            move.total_exoneration_amount = sum(exoneration_lines.mapped('exoneration_amount'))
            move.has_exoneration_lines = bool(exoneration_lines)

    # ==============================================================================================
    #                                  INTEGRACIÓN CON EXONERACIONES
    # ==============================================================================================

    def _get_exoneration_for_line(self, invoice_line):
        """
        ✅ DEBUG COMPLETO: Obtiene la exoneración aplicable para una línea de factura
        """
        _logger.info("=" * 80)
        _logger.info("🔍 INICIANDO DEBUG DE EXONERACIÓN")
        _logger.info("=" * 80)

        # 1. Verificar cliente
        _logger.info(f"👤 Cliente: {self.partner_id.name}")
        _logger.info(f"📋 Cliente ID: {self.partner_id.id}")
        _logger.info(f"✅ Tiene exoneraciones activas: {self.partner_id.has_exoneration_new}")

        if not self.partner_id.has_exoneration_new:
            _logger.error("❌ CLIENTE NO TIENE EXONERACIONES ACTIVAS")
            return False

        # 2. Verificar producto
        _logger.info(f"🛍️ Producto: {invoice_line.product_id.name if invoice_line.product_id else 'SIN PRODUCTO'}")

        if not invoice_line.product_id:
            _logger.error("❌ LÍNEA SIN PRODUCTO")
            return False

        # 3. Buscar código CABYS
        cabys_code = None

        # Método 1: Código directo del producto
        if hasattr(invoice_line.product_id, 'cabys_code'):
            cabys_code = invoice_line.product_id.cabys_code
            _logger.info(f"🏷️ Código CABYS del producto: '{cabys_code}'")
        else:
            _logger.warning("⚠️ Producto no tiene atributo 'cabys_code'")

        # Método 2: Desde cabys_product_id (integración módulo CABYS)
        if not cabys_code and hasattr(invoice_line.product_id, 'cabys_product_id'):
            if invoice_line.product_id.cabys_product_id:
                cabys_code = invoice_line.product_id.cabys_product_id.codigo
                _logger.info(f"🏷️ Código CABYS desde cabys_product_id: '{cabys_code}'")

        # Método 3: Desde categoría
        if not cabys_code and invoice_line.product_id.categ_id:
            if hasattr(invoice_line.product_id.categ_id, 'cabys_code'):
                cabys_code = invoice_line.product_id.categ_id.cabys_code
                _logger.info(f"🏷️ Código CABYS desde categoría: '{cabys_code}'")

        if not cabys_code:
            _logger.error(f"❌ NO SE ENCONTRÓ CÓDIGO CABYS PARA PRODUCTO: {invoice_line.product_id.name}")
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

            # Debug adicional: Listar exoneraciones del cliente
            client_exonerations = self.partner_id.exoneration_ids.filtered(
                lambda e: e.active and e.is_valid_today()
            )
            _logger.info(f"📊 Cliente tiene {len(client_exonerations)} exoneraciones activas")

            for exo in client_exonerations:
                _logger.info(f"   📋 {exo.exoneration_number} - {exo.cabys_count} códigos CABYS")

        _logger.info("=" * 80)
        return exoneration

    def debug_tax_calculation(self):
        """
        🔧 MÉTODO DE DEBUG: Prueba el cálculo de impuestos con exoneración
        """
        _logger.info("=" * 80)
        _logger.info("🧮 DEBUG DE CÁLCULO DE IMPUESTOS")
        _logger.info("=" * 80)

        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            _logger.info(f"\n📝 LÍNEA: {line.product_id.name}")

            # 1. Buscar exoneración
            exoneration = self._get_exoneration_for_line(line)

            # 2. Calcular impuestos
            if line.tax_ids and exoneration:
                for tax in line.tax_ids:
                    _logger.info(f"💰 Impuesto: {tax.name} - {tax.amount}%")
                    _logger.info(f"💵 Base: ₡{line.price_subtotal:,.2f}")

                    tax_calc = self._calculate_tax_with_exoneration(
                        tax, line.price_subtotal, exoneration
                    )

                    _logger.info(f"📊 RESULTADOS DE CÁLCULO:")
                    _logger.info(f"   🏷️ IVA Bruto: ₡{tax_calc['tax_amount']:,.2f}")
                    _logger.info(f"   🎁 Exoneración: -₡{tax_calc['exoneration_amount']:,.2f}")
                    _logger.info(f"   💸 IVA Neto: ₡{tax_calc['net_tax_amount']:,.2f}")
            else:
                _logger.warning("⚠️ Sin impuestos o sin exoneración para esta línea")

        _logger.info("=" * 80)

    def _calculate_tax_with_exoneration(self, tax, base_amount, exoneration):
        """
        Calcula el impuesto aplicando la exoneración correspondiente

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

    @api.model
    def _prepare_exoneration_xml_data(self, exoneration, exoneration_amount):
        """
        Prepara los datos de exoneración para incluir en el XML de Hacienda

        Args:
            exoneration: Registro de exoneración
            exoneration_amount: Monto exonerado

        Returns:
            dict: Datos para el XML
        """
        return {
            'TipoDocumento': exoneration.exoneration_type_id.code if exoneration.exoneration_type_id else '02',
            'NumeroDocumento': exoneration.exoneration_number,
            'NombreInstitucion': exoneration.institution_name or 'No especificada',
            'FechaEmision': exoneration.date_issue.strftime(
                '%Y-%m-%dT00:00:00-06:00') if exoneration.date_issue else '',
            'PorcentajeExoneracion': int(exoneration.percentage_exoneration),
            'MontoExoneracion': exoneration_amount,
        }

    # -------------------------------------------------------------------------
    # OVERRIDE METHODS PARA INTEGRACIÓN
    # -------------------------------------------------------------------------

    def action_post(self):
        """Override para validar exoneraciones antes de confirmar"""
        for move in self:
            if (move.move_type in ('out_invoice', 'out_refund') and
                    move.partner_id.has_exoneration_new and
                    move.has_exoneration_lines):

                # Validar que las exoneraciones estén vigentes
                expired_exonerations = []
                for line in move.invoice_line_ids.filtered(lambda l: l.has_exoneration):
                    if line.exoneration_id and not line.exoneration_id.is_valid_today():
                        expired_exonerations.append(line.exoneration_id.exoneration_number)

                if expired_exonerations:
                    from odoo.exceptions import UserError
                    raise UserError(
                        _('Las siguientes exoneraciones han vencido: %s. '
                          'Por favor actualice las exoneraciones antes de facturar.') %
                        ', '.join(set(expired_exonerations))
                    )

        return super().action_post()

    # -------------------------------------------------------------------------
    # MÉTODOS DE UTILIDAD PARA GENERACIÓN XML
    # -------------------------------------------------------------------------

    def get_exoneration_xml_data(self):
        """
        ✅ CORREGIDO: Solo incluye exoneraciones para líneas que realmente las tienen
        """
        exoneration_data = []

        if not self.has_exoneration_lines:
            _logger.info("ℹ️ Factura sin líneas de exoneración")
            return exoneration_data

        # 🔍 LOGS DE DEBUGGING
        _logger.info("=" * 80)
        _logger.info("🌐 DEBUG GENERACIÓN XML EXONERACIONES")
        _logger.info("=" * 80)
        _logger.info(f"📄 Factura: {self.name}")

        exonerated_lines = self.invoice_line_ids.filtered(lambda l: l.has_exoneration)
        _logger.info(f"📊 Líneas con exoneración: {len(exonerated_lines)}")
        _logger.info(f"📊 Total líneas: {len(self.invoice_line_ids)}")

        for line in exonerated_lines:
            if line.exoneration_id and line.tax_ids:
                _logger.info(f"🛍️ Procesando línea: {line.product_id.name}")
                _logger.info(f"   🏷️ Código CABYS: {line._get_product_cabys_code()}")
                _logger.info(f"   📋 Exoneración: {line.exoneration_id.exoneration_number}")
                _logger.info(f"   💰 Monto exonerado: ₡{line.exoneration_amount:,.2f}")

                for tax in line.tax_ids:
                    # ⚠️ VALIDACIÓN CRÍTICA: Solo incluir si realmente tiene exoneración
                    if line.exoneration_amount > 0:
                        xml_data = {
                            'TipoDocumento': line.exoneration_id.exoneration_type_id.code if line.exoneration_id.exoneration_type_id else '02',
                            'NumeroDocumento': line.exoneration_id.exoneration_number,
                            'NombreInstitucion': line.exoneration_id.institution_name or 'No especificada',
                            'FechaEmision': line.exoneration_id.date_issue.strftime(
                                '%Y-%m-%dT00:00:00-06:00') if line.exoneration_id.date_issue else '',
                            'PorcentajeExoneracion': int(line.exoneration_id.percentage_exoneration * 100),
                            'MontoExoneracion': line.exoneration_amount,
                            'line_id': line.id,
                            'tax_id': tax.id,
                            'cabys_code': line._get_product_cabys_code(),  # Para debugging
                        }
                        exoneration_data.append(xml_data)
                        _logger.info(f"✅ Datos XML agregados para línea {line.id}")
                    else:
                        _logger.warning(f"⚠️ Línea {line.id} marcada con exoneración pero monto = 0")

        _logger.info(f"📦 Total registros XML exoneración: {len(exoneration_data)}")
        _logger.info("=" * 80)
        return exoneration_data

    def debug_exoneration_application(self):
        """
        🔧 MÉTODO DE DEBUG: Verifica la aplicación de exoneraciones línea por línea
        """
        _logger.info("=" * 100)
        _logger.info("🧪 DEBUG COMPLETO: APLICACIÓN DE EXONERACIONES")
        _logger.info("=" * 100)
        _logger.info(f"📄 Factura: {self.name}")
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
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
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