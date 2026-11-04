# -*- coding: utf-8 -*-
import base64
import datetime
import logging
import re
from xml.sax.saxutils import escape

import pytz
from lxml import etree
from markupsafe import Markup
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from odoo.tools.misc import get_lang

from .. import extensions
from . import api_facturae
from .qr_generator import GenerateQrCode

_logger = logging.getLogger(__name__)


class AccountInvoiceElectronic(models.Model):
    _description = "Account Invoice Electronic"
    _inherit = "account.move"

    # ==============================================================================================
    #                                          INVOICE
    # ==============================================================================================

    # NOTE: Client and CABYS validation logic is provided by fe.validation.service

    # === Electronic Number Reference fields === #
    number_electronic = fields.Char(string="Electronic number", copy=False, index=True)
    sequence = fields.Char(string="Consecutive", readonly=True, copy=False)
    date_issuance = fields.Char(string="Date of issue", copy=False)
    consecutive_number_receiver = fields.Char(
        string="Consecutive Receiver Number", copy=False, readonly=True, index=True
    )
    tipo_documento = fields.Selection(
        selection=[
            ("FE", "Factura Electrónica"),
            ("FEE", "Factura Electrónica de Exportación"),
            ("TE", "Tiquete Electrónico"),
            ("REP", "Recibo Electrónico de Pago"),
            ("NC", "Nota de Crédito"),
            ("ND", "Nota de Débito"),
            ("CCE", "MR Aceptación"),
            ("CPCE", "MR Aceptación Parcial"),
            ("RCE", "MR Rechazo"),
            ("FEC", "Factura Electrónica de Compra"),
            ("disabled", "Electronic Documents Disabled"),
        ],
        string="Voucher Type",
        default="FE",
        help="Indicates the type of document according to the classification of the Ministerio de Hacienda",
    )
    invoice_usd_currency_rate = fields.Float(
        string="Currency Rate (USD)", compute="_compute_invoice_usd_currency_rate"
    )

    # === Answers fields === #

    state_send_invoice = fields.Selection(
        selection=[
            ("aceptado", "Aceptado"),
            ("rechazado", "Rechazado"),
            ("error", "Error"),
            ("na", "No Aplica"),
            ("ne", "No Encontrado"),
            ("firma_invalida", "Firma Inválida"),
            ("procesando", "Procesando"),
        ],
        string="Estado FE Proveedor",
    )
    state_tributacion = fields.Selection(
        selection=[
            ("aceptado", "Aceptado"),
            ("rechazado", "Rechazado"),
            ("recibido", "Recibido"),
            ("firma_invalida", "Firma Inválida"),
            ("error", "Error"),
            ("procesando", "Procesando"),
            ("na", "No Aplica"),
            ("ne", "No Encontrado"),
        ],
        string="Estado FE",
        copy=False,
    )
    state_invoice_partner = fields.Selection(
        selection=[("1", "Aceptado"), ("2", "Aceptacion parcial"), ("3", "Rechazado")],
        string="Respuesta del Cliente",
    )

    # === Economic Activity fields === #
    economic_activity_id = fields.Many2one(
        comodel_name="economic.activity",
        string="Economic Activity",
        context={"active_test": False},
        # check_company=True
    )
    economic_activities_ids = fields.Many2many(
        comodel_name="economic.activity",
        string="Economic activities",
        compute="_compute_economic_activities",
        context={"active_test": False},
        # check_company=True
    )
    partner_economic_activity_id = fields.Many2one(
        comodel_name="economic.activity",
        string="Vendor Economic Activity",
        context={"active_test": False},
        # check_company=True
    )

    partner_economic_activities_ids = fields.Many2many(
        comodel_name="economic.activity",
        string="Vendor Economic Activities",
        compute="_compute_economic_activities",
        context={"active_test": False},
        # check_company=True
    )

    # === Reference fields === #

    reference_code_id = fields.Many2one(
        comodel_name="reference.code", string="Reference code"
    )
    reference_document_id = fields.Many2one(
        comodel_name="reference.document", string="Reference Document Type"
    )
    payment_methods_id = fields.Many2one(
        comodel_name="payment.methods", string="Payment methods"
    )
    invoice_id = fields.Many2one(
        comodel_name="account.move", string="Reference document", copy=False
    )
    electronic_invoice_return_message = fields.Char(
        string="Hacienda answer", readonly=True
    )
    not_loaded_invoice = fields.Char(
        string="Original Invoice Number not loaded", readonly=True
    )
    not_loaded_invoice_date = fields.Date(
        string="Original Invoice Date not loaded", readonly=True
    )

    # === Amount fields === #

    amount_discount_electronic_invoice = fields.Monetary(
        string="Discount Amount",
        compute="_compute_amount_discount_electronic_invoice",
        readonly=True,
        store=True,
    )
    amount_tax_electronic_invoice = fields.Monetary(
        string="Total FE taxes", readonly=True
    )
    amount_total_electronic_invoice = fields.Monetary(string="Total FE", readonly=True)
    amount_iva_returned = fields.Monetary(
        string="IVA Returned", readonly=True, store=True
    )
    
    # =========================================================================
    # NUEVOS CAMPOS DE EXONERACIÓN 
    # =========================================================================

    # Indica si la factura tiene exoneración (basado en el partner)
    has_exoneration = fields.Boolean(
        string="Tiene Exoneración",
        compute="_compute_exoneration_amounts",
        default=False,
        store=True,
        help="Indica si el cliente tiene exoneración vigente",
    )

    # Porcentaje de exoneración del cliente
    exoneration_percentage = fields.Float(
        string="Porcentaje de Exoneración",
        compute="_compute_exoneration_amounts",
        default=0.0,
        store=True,
        help="Porcentaje de exoneración del cliente (del partner)",
    )

    # Monto total del impuesto exonerado (lo que se ahorra el cliente)
    amount_exoneration = fields.Monetary(
        string="Monto Exoneración",
        compute="_compute_exoneration_amounts",
        default=0.0,
        store=True,
        help="Monto total del impuesto exonerado en esta factura",
    )

    # Total del impuesto antes de exoneración (impuesto completo)
    amount_tax_before_exoneration = fields.Monetary(
        string="Impuesto Antes de Exoneración",
        compute="_compute_exoneration_amounts",
        default=0.0,
        store=True,
        help="Monto total del impuesto antes de aplicar la exoneración",
    )

    # Total a pagar después de exoneración (esto es el amount_total normal de Odoo)
    # Lo agregamos como campo relacionado para claridad en la vista
    amount_total_to_pay = fields.Monetary(
        string="Total a Pagar",
        related="amount_total",
        store=True,
        readonly=True,
        help="Total a pagar después de aplicar la exoneración",
    )

    # Campos relacionados del partner para información de exoneración
    partner_exoneration_number = fields.Char(
        string="Número de Exoneración",
        related="partner_id.exoneration_number",
        store=True,
        readonly=True,
    )

    partner_type_exoneration = fields.Many2one(
        comodel_name="aut.ex",
        string="Tipo de Autorización",
        related="partner_id.type_exoneration",
        store=True,
        readonly=True,
    )

    partner_exoneration_institution_id = fields.Many2one(
        string="Institución Emisora",
        related="partner_id.institution_id",
        store=True,
        readonly=True,
    )

    partner_exoneration_expiry = fields.Date(
        string="Fecha Vencimiento Exoneración",
        related="partner_id.date_expiration",
        store=True,
        readonly=True,
    )

    # === XML fields === #

    xml_respuesta_tributacion = fields.Binary(
        string="XML Tributación Response", copy=False, attachment=True
    )
    fname_xml_respuesta_tributacion = fields.Char(
        string="XML File Name Tributación Response", copy=False
    )

    xml_comprobante = fields.Binary(string="XML voucher", copy=False, attachment=True)
    fname_xml_comprobante = fields.Char(string="File name XML voucher", copy=False)

    xml_supplier_approval = fields.Binary(
        string="Vendor XML", copy=False, attachment=True
    )
    fname_xml_supplier_approval = fields.Char(
        string="Vendor XML voucher file name", copy=False
    )

    # === Misc Information === #

    qr_image = fields.Image(
        string="QR Code", max_width=100, max_height=100, compute="_compute_qr_code"
    )
    partner_vat = fields.Char(
        string="Partner Tax ID",
        related="partner_id.vat",
        store=True,
        index=True,
        help="The Parnter Tax Identification Number.",
    )
    company_vat = fields.Char(
        string="Company Tax ID",
        related="partner_id.vat",
        store=True,
        index=True,
        help="Your Company Tax Identification Number.",
    )
    invoice_amount_text = fields.Char(
        string="Amount in Letters", readonly=True, copy=False
    )
    state_email = fields.Selection(
        selection=[
            ("no_email", "Sin cuenta de correo"),
            ("sent", "Enviado"),
            ("fe_error", "Error FE"),
        ],
        string="Estado email",
        copy=False,
    )
    ignore_total_difference = fields.Boolean(
        string="Ignore Difference in Totals", default=False
    )
    error_count = fields.Integer(string="Electronic Inv. Error Count", default="0", copy=False)

    # Computed fields for UI: indicates if invoice has immutable electronic document
    einvoice_is_immutable = fields.Boolean(
        string="E-Invoice Immutable",
        compute="_compute_einvoice_is_immutable",
        help="True if invoice has an electronic document in protected state (cannot be modified)",
    )

    # Persistent field: tracks if invoice had a rejected electronic invoice
    # Once set to True, this invoice cannot generate new FE data, only be cancelled
    einvoice_had_rejection = fields.Boolean(
        string="FE Rechazada",
        default=False,
        copy=False,
        readonly=True,
        help="Indica que esta factura tuvo un comprobante electrónico rechazado por Hacienda. "
        "No se puede generar una nueva factura electrónica desde este documento. "
        "La factura solo puede ser cancelada.",
    )

    _number_electronic_uniq = models.Constraint(
        "unique (company_id, number_electronic)",
        "La clave de comprobante debe ser única",
    )

    # -------------------------------------------------------------------------
    # ELECTRONIC INVOICE PROTECTED DOCUMENT TYPES
    # -------------------------------------------------------------------------
    # Document types that represent electronic invoices sent to Hacienda
    # FE: Factura Electrónica, FEE: Factura Electrónica de Exportación
    # TE: Tiquete Electrónico, NC: Nota de Crédito, ND: Nota de Débito
    EINVOICE_PROTECTED_TYPES = ("FE", "FEE", "TE", "NC", "ND")

    # -------------------------------------------------------------------------
    # ELECTRONIC INVOICE STATE HELPERS
    # -------------------------------------------------------------------------

    def _compute_einvoice_is_immutable(self):
        """Compute if invoice has a protected (immutable) electronic document."""
        for move in self:
            has_protected, _ = move._has_protected_einvoice()
            move.einvoice_is_immutable = has_protected

    def _has_protected_einvoice(self):
        """
        Check if move has an electronic invoice that should be preserved.

        Protected states:
        - 'procesando': Document sent, awaiting Hacienda response
        - 'aceptado': Document accepted by Hacienda
        - 'recibido': Document received by Hacienda

        Returns:
            tuple: (has_protected: bool, state: str or False)
        """
        self.ensure_one()
        if not self.number_electronic:
            return False, False

        # Check if this is an electronic invoice type
        if self.tipo_documento not in self.EINVOICE_PROTECTED_TYPES:
            return False, False

        protected_states = ("procesando", "aceptado", "recibido")
        state = self.state_tributacion
        return state in protected_states, state

    def _has_rejected_einvoice(self):
        """
        Check if move has a rejected electronic invoice that can be cleared.

        Returns:
            bool: True if electronic invoice exists and was rejected
        """
        self.ensure_one()
        if not self.number_electronic:
            return False

        # Check if this is an electronic invoice type
        if self.tipo_documento not in self.EINVOICE_PROTECTED_TYPES:
            return False

        return self.state_tributacion == "rechazado"

    # -------------------------------------------------------------------------
    # OVERRIDE: button_draft - Block reset when electronic invoice exists
    # -------------------------------------------------------------------------

    def button_draft(self):
        """
        Override to block reset to draft when move has a protected electronic invoice.

        Behavior:
        - Protected document (procesando/aceptado/recibido): BLOCK reset with UserError.
          The invoice cannot be reverted to draft once sent/accepted by Hacienda.
        - Rejected document: Allow reset BUT preserve FE data and mark as had rejection.
          The invoice can only be cancelled, NOT used to generate a new FE.
        - No electronic invoice: Standard behavior.
        """
        for move in self:
            has_protected, state = move._has_protected_einvoice()

            if has_protected:
                # BLOCK: Cannot reset invoice with protected electronic document
                state_label = dict(self._fields["state_tributacion"].selection).get(
                    state, state
                )
                raise UserError(
                    _(
                        "Este documento tiene un comprobante electrónico con estado '%s' "
                        "y no puede ser pasado a borrador.\n\n"
                        "Clave electrónica: %s\n"
                        "Tipo de documento: %s\n\n"
                        "Los documentos electrónicos enviados o aceptados por Hacienda "
                        "son inmutables y no pueden ser modificados."
                    )
                    % (state_label, move.number_electronic, move.tipo_documento)
                )

            if move._has_rejected_einvoice():
                # Allow reset for rejected documents BUT preserve FE data
                # Mark as having had a rejection - this blocks future FE generation
                move.einvoice_had_rejection = True
                _logger.info(
                    "Move %s reset to draft with rejected electronic invoice. "
                    "FE data preserved. einvoice_had_rejection flag set to True. "
                    "Invoice can only be cancelled, not regenerated.",
                    move.name,
                )

        return super(AccountInvoiceElectronic, self).button_draft()

    # -------------------------------------------------------------------------
    # CONSTRAINT METHODS
    # -------------------------------------------------------------------------

    # ==============================================================================================
    # CONSTRAINT PARA VALIDAR CABYS AUTORIZADO (actualizar existente)
    # ==============================================================================================


    @api.depends("partner_id")
    @api.constrains("line_ids")
    def _check_allowed_cabys_code(self):
        """
        Verificar que los códigos CABYS estén autorizados para exoneración.
        
        Según v4.4: En caso de aplicarse exoneración, el código CABYS indicado por el emisor 
        debe encontrarse en la autorización emitida por la Dirección General de Hacienda.
        
        IMPORTANTE: Si un CABYS no está autorizado, la línea se procesa con IVA normal.
        Esta constraint solo es informativa, no bloquea la factura.
        """
        for move in self:
            partner_id = move.partner_id
            
            # Solo validar si el partner tiene exoneración
            if not partner_id or not partner_id.has_exoneration:
                continue
            
            # Obtener códigos CABYS autorizados
            if partner_id.allowed_cabys_ids:
                allowed_codes = [code.name for code in partner_id.allowed_cabys_ids]
            else:
                # Si no hay códigos específicos, permitir todos (para retrocompatibilidad)
                continue
            
            # Verificar cada línea de producto
            unauthorized_lines = []
            for line in move.line_ids.filtered(lambda x: x.display_type == "product" and x.cabys_code):
                _logger.info(_("Verificando código CABYS: %s") % line.cabys_code)
                
                if line.cabys_code not in allowed_codes:
                    unauthorized_lines.append({
                        'product': line.name[:50] if line.name else "Sin nombre",
                        'cabys': line.cabys_code
                    })
            
            # Si hay líneas no autorizadas, mostrar mensaje informativo (NO error)
            if unauthorized_lines:
                msg_lines = []
                for item in unauthorized_lines:
                    msg_lines.append(f"• {item['product']} (CABYS: {item['cabys']})")
                
                info_msg = _(
                    "Las siguientes líneas tienen códigos CABYS no autorizados para exoneración "
                    "y se procesarán con IVA normal:\n%s"
                ) % "\n".join(msg_lines)
                
                _logger.info(info_msg)
                move.message_post(
                    subject=_("Información - CABYS no autorizados"), 
                    body=info_msg
                )
            

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    
    """
    =================================================================
    MÉTODO _compute_exoneration_amounts v18 - CON VERIFICACIÓN CABYS
    =================================================================

    Verifica si cada línea de producto tiene CABYS autorizado antes de 
    calcular la exoneración.
    """

    @api.depends(
        "partner_id",
        "partner_id.has_exoneration",
        "partner_id.percentage_exoneration",
        "partner_id.date_expiration",
        "partner_id.allowed_cabys_ids",
        "invoice_line_ids.tax_ids",
        "invoice_line_ids.price_subtotal",
        "invoice_line_ids.product_id.cabys_code",
        "invoice_line_ids.product_id.categ_id.cabys_code",
    )
    def _compute_exoneration_amounts(self):
        """
        Calcula los montos de exoneración.
        
        IMPORTANTE: Solo se calcula exoneración para productos 
        cuyo CABYS esté en allowed_cabys_ids del partner.
        """
        for move in self:
            # Inicializar valores
            move.has_exoneration = False
            move.exoneration_percentage = 0.0
            move.amount_exoneration = 0.0
            move.amount_tax_before_exoneration = 0.0

            partner = move.partner_id
            if not partner or not partner.has_exoneration:
                continue

            # Verificar que la exoneración no esté vencida
            if partner.date_expiration and partner.date_expiration < datetime.date.today():
                continue

            exoneration_points = partner.percentage_exoneration
            if exoneration_points <= 0:
                continue

            # Obtener códigos CABYS autorizados
            allowed_codes = []
            if partner.allowed_cabys_ids:
                allowed_codes = [code.name for code in partner.allowed_cabys_ids]

            total_tax_full = 0.0
            total_exoneration = 0.0
            total_lines_authorized = 0
            total_lines_with_tax = 0

            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                if not line.tax_ids:
                    continue

                subtotal = line.price_subtotal

                # Obtener CABYS del producto
                cabys_code = None
                if line.product_id:
                    if line.product_id.cabys_code:
                        cabys_code = line.product_id.cabys_code
                    elif line.product_id.categ_id and line.product_id.categ_id.cabys_code:
                        cabys_code = line.product_id.categ_id.cabys_code

                # Verificar si CABYS está autorizado
                cabys_authorized = True  # Por defecto autorizado (si no hay restricción)
                if allowed_codes and cabys_code:
                    cabys_authorized = cabys_code in allowed_codes

                for tax in line.tax_ids:
                    # Solo considerar impuestos IVA (código 01 o 04)
                    tax_code = tax.tax_code
                    
                    if tax_code not in ['01', '04']:
                        continue

                    tax_rate = tax.amount
                    tax_amount_full = subtotal * (tax_rate / 100.0)
                    total_tax_full += tax_amount_full
                    total_lines_with_tax += 1

                    # Solo calcular exoneración si CABYS está autorizado
                    if cabys_authorized:
                        effective_exoneration_points = min(exoneration_points, tax_rate)
                        exoneration_amount = subtotal * (effective_exoneration_points / 100.0)
                        total_exoneration += exoneration_amount
                        total_lines_authorized += 1
                    else:
                        _logger.debug(
                            "Producto %s: CABYS %s no autorizado, IVA normal",
                            line.name[:30], cabys_code
                        )

            # Calcular porcentaje de exoneración efectivo
            exoneration_pct = 0.0
            if total_tax_full > 0:
                exoneration_pct = (total_exoneration / total_tax_full) * 100

            # Solo marcar como tiene exoneración si hay monto exonerado
            if total_exoneration > 0:
                move.has_exoneration = True
                move.exoneration_percentage = exoneration_pct
                move.amount_tax_before_exoneration = round(total_tax_full, 2)
                move.amount_exoneration = round(total_exoneration, 2)
            
            _logger.debug(
                "Factura %s: IVA total=%s, Exoneración=%s, Líneas autorizadas=%s/%s",
                move.name, round(total_tax_full, 2), round(total_exoneration, 2),
                total_lines_authorized, total_lines_with_tax
            )


    @api.depends(
        "invoice_line_ids.discount",
        "invoice_line_ids.price_unit",
        "invoice_line_ids.quantity",
    )
    def _compute_amount_discount_electronic_invoice(self):
        for move in self:
            total_discount = 0.0
            for line in move.invoice_line_ids:
                # Calcula el descuento por línea
                # (precio unitario * cantidad) * (descuento %)
                discount_amount_line = (line.price_unit * line.quantity) * (
                    line.discount / 100.0
                )
                total_discount += discount_amount_line
            move.amount_discount_electronic_invoice = total_discount

    def _compute_invoice_usd_currency_rate(self):
        for move in self:
            if move.currency_id.display_name == "USD":
                move.invoice_usd_currency_rate = 1 / move.currency_id.rate
            else:
                move.invoice_usd_currency_rate = 1

    @api.depends("amount_total")
    def update_text_amount(self):
        for inv in self:
            inv.invoice_amount_text = extensions.text_converter.number_to_text_es(
                inv.amount_total
            )

    def _compute_qr_code(self):
        for record in self:
            qr_info = ""
            if record.company_id.invoice_qr_type != "by_info":
                qr_info = (
                    record.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
                )
                qr_info += record.get_portal_url()
            else:
                if record.company_id.invoice_field_ids:
                    dict_result = {}
                    for ffild in record.company_id.invoice_field_ids.mapped("field_id"):
                        if ffild.ttype == "many2one":
                            dict_result[ffild.field_description] = record[
                                ffild.name
                            ].display_name
                        else:
                            dict_result[ffild.field_description] = record[ffild.name]
                    for key, value in dict_result.items():
                        if str(key).__contains__("Partner") or str(key).__contains__(
                            _("Partner")
                        ):
                            if record.move_type in ["out_invoice", "out_refund"]:
                                key = str(key).replace(_("Partner"), _("Customer"))
                            elif record.move_type in ["in_invoice", "in_refund"]:
                                key = str(key).replace(_("Partner"), _("Vendor"))
                        qr_info += f"{key} : {value} <br/>"
                    qr_info = html2plaintext(qr_info)
            record.qr_image = GenerateQrCode.generate_qr_code(qr_info)

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.depends("partner_id", "company_id", "move_type")
    def _compute_economic_activities(self):
        for inv in self:
            # Para Facturas de compra se asigna el campo partner_economic_activity_id
            inv.partner_economic_activities_ids = False
            if inv.move_type in ("in_invoice", "in_refund"):
                if inv.partner_id:
                    inv.partner_economic_activities_ids = (
                        inv.partner_id.economic_activities_ids
                        if inv.partner_id.economic_activities_ids
                        else False
                    )
                    inv.partner_economic_activity_id = inv.partner_id.activity_id

            inv.economic_activities_ids = (
                self.env["economic.activity"].sudo().search([
                    ("active", "=", True),
                    ("company_id", "=", inv.company_id.id)
                ])
            )

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        super()._onchange_partner_id()
        self.payment_methods_id = self.partner_id.payment_methods_id
        self.economic_activities_ids = self.env["economic.activity"].search(
            [("active", "=", True), ("company_id", "=", self.company_id.id)]
        )
        self.economic_activity_id = self.company_id.activity_id or (self.economic_activities_ids[:1])

        if self.move_type in ("in_invoice", "in_refund"):
            if self.partner_id:
                self.partner_economic_activities_ids = (
                    self.partner_id.economic_activities_ids
                )
                self.partner_economic_activity_id = self.partner_id.activity_id
            else:
                self.partner_economic_activity_id = False
                self.partner_economic_activities_ids = []

        if self.partner_id and self.partner_id.export:
            self.tipo_documento = "FEE"
        elif self.move_type == "out_refund":
            self.tipo_documento = "NC"
        elif self.partner_id and self.partner_id.vat:
            if self.partner_id.country_id and self.partner_id.country_id.code != "CR":
                self.tipo_documento = "TE"
            elif (
                self.partner_id.identification_id
                and self.partner_id.identification_id.code == "05"
            ):
                self.tipo_documento = "TE"
            else:
                self.tipo_documento = "FE"
        else:
            self.tipo_documento = "TE"

    @api.onchange("xml_supplier_approval")
    def _onchange_xml_supplier_approval(self):
        if self.xml_supplier_approval:
            xml_decoded = base64.b64decode(self.xml_supplier_approval)
            try:
                factura = etree.fromstring(xml_decoded)
            except Exception as e:
                _logger.info(
                    "E-INV CR - This XML file is not XML-compliant.  Exception %s", e
                )
                return {"status": 400, "text": "Excepción de conversión de XML"}

            pretty_xml_string = etree.tostring(
                factura, pretty_print=True, encoding="UTF-8", xml_declaration=True
            )
            _logger.error("E-INV CR - send_file XML: %s", pretty_xml_string)
            namespaces = factura.nsmap
            inv_xmlns = namespaces.pop(None)
            namespaces["inv"] = inv_xmlns
            if not factura.xpath("inv:Clave", namespaces=namespaces):
                title = "Attention"
                message = _("The xml file does not contain the Clave node. ")
                message += _("Please upload a file with the correct format.")
                return {
                    "value": {"xml_supplier_approval": False},
                    "warning": {"title": title, "message": message},
                }

            if not factura.xpath("inv:FechaEmision", namespaces=namespaces):
                title = "Attention"
                message = _("The xml file does not contain the FechaEmision node. ")
                message += _("Please upload a file with the correct format.")
                return {
                    "value": {"xml_supplier_approval": False},
                    "warning": {"title": title, "message": message},
                }

            if not factura.xpath(
                "inv:Emisor/inv:Identificacion/inv:Numero", namespaces=namespaces
            ):
                title = "Attention"
                message = _("The xml file does not contain the Emisor node. ")
                message += _("Please upload a file with the correct format.")
                return {
                    "value": {"xml_supplier_approval": False},
                    "warning": {"title": title, "message": message},
                }

            if not factura.xpath(
                "inv:ResumenFactura/inv:TotalComprobante", namespaces=namespaces
            ):
                title = "Attention"
                message = _("The TotalComprobante node cannot be located. ")
                message += _("Please upload a file with the correct format.")
                return {
                    "value": {"xml_supplier_approval": False},
                    "warning": {"title": title, "message": message},
                }

        else:
            self.state_tributacion = False
            self.xml_supplier_approval = False
            self.fname_xml_supplier_approval = False
            self.xml_respuesta_tributacion = False
            self.fname_xml_respuesta_tributacion = False
            self.date_issuance = False
            self.number_electronic = False
            self.state_invoice_partner = False

    # -------------------------------------------------------------------------
    # TOOLING
    # -------------------------------------------------------------------------

    def load_xml_data(self):
        account = False
        analytic_account = False
        product = False

        purchase_journal = self.env["account.journal"].search(
            [("type", "=", "purchase")], limit=1
        )
        default_account_id = purchase_journal.expense_account_id.id
        if default_account_id:
            account = self.env["account.account"].search(
                [("id", "=", default_account_id)], limit=1
            )
            load_lines = purchase_journal.load_lines
        else:
            default_account_id = (
                self.env["ir.config_parameter"].sudo().get_param("expense_account_id")
            )
            load_lines = bool(
                self.env["ir.config_parameter"].sudo().get_param("load_lines")
            )
            if default_account_id:
                account = self.env["account.account"].search(
                    [("id", "=", default_account_id)], limit=1
                )

        analytic_account_id = purchase_journal.expense_analytic_account_id.id
        if analytic_account_id:
            analytic_account = self.env["account.analytic.account"].search(
                [("id", "=", analytic_account_id)], limit=1
            )
        else:
            analytic_account_id = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("expense_analytic_account_id")
            )
            if analytic_account_id:
                analytic_account = self.env["account.analytic.account"].search(
                    [("id", "=", analytic_account_id)], limit=1
                )

        product_id = purchase_journal.expense_product_id.id
        if product_id:
            product = self.env["product.product"].search(
                [("id", "=", product_id)], limit=1
            )
        else:
            product_id = (
                self.env["ir.config_parameter"].sudo().get_param("expense_product_id")
            )
            if product_id:
                product = self.env["product.product"].search(
                    [("id", "=", product_id)], limit=1
                )

        api_facturae.load_xml_data(self, load_lines, account, product, analytic_account)

    def action_register_payment(self):
        """
        Override to enforce single-invoice payment restriction for Customer Invoices.
        Avoid to generate REP from multiple invoices at once.
        """
        # Filter for Customer Invoices
        out_invoices = self.filtered(lambda m: m.move_type == "out_invoice")

        # If selection contains Customer Invoices and count > 1, Block.
        if len(out_invoices) > 1:
            raise UserError(_("Payments must be registered one invoice at a time."))

        return super().action_register_payment()

    def get_invoice_sequence(self):
        tipo_documento = self.tipo_documento
        sequence = False
        no_sequence_message = (
            "This journal doesn't have the sequence configure for documents of type: "
        )
        no_sequence_message += tipo_documento
        no_sequence_message += ". Please consider to configure the sequence and reset the invoice to draft."

        if self.move_type == "out_invoice":
            # tipo de identificación
            if (
                self.partner_id
                and self.partner_id.vat
                and not self.partner_id.identification_id
            ):
                raise UserError(
                    _("Select the type of client identification in your profile")
                )

            if tipo_documento == "FE" and (
                not self.partner_id.vat
                or self.partner_id.identification_id.code == "05"
                or self.partner_id.inscribed == False
            ):
                tipo_documento = "TE"
                self.tipo_documento = "TE"

            if tipo_documento == "FE":
                if self.journal_id.FE_sequence_id:
                    sequence = self.journal_id.FE_sequence_id.with_company(
                        self.company_id
                    )._next()
                else:
                    self.state_tributacion = "na"
                    self.message_post(subject=_("Warning"), body=no_sequence_message)

            elif tipo_documento == "TE":
                if self.journal_id.TE_sequence_id:
                    sequence = self.journal_id.TE_sequence_id.with_company(
                        self.company_id
                    )._next()
                else:
                    self.state_tributacion = "na"
                    self.message_post(subject=_("Warning"), body=no_sequence_message)

            elif tipo_documento == "ND":
                if self.journal_id.ND_sequence_id:
                    sequence = self.journal_id.ND_sequence_id.with_company(
                        self.company_id
                    )._next()
                else:
                    self.state_tributacion = "na"
                    self.message_post(subject=_("Warning"), body=no_sequence_message)

            elif tipo_documento == "FEE":
                if self.journal_id.FEE_sequence_id:
                    sequence = self.journal_id.FEE_sequence_id.with_company(
                        self.company_id
                    )._next()
                else:
                    self.state_tributacion = "na"
                    self.message_post(subject=_("Warning"), body=no_sequence_message)
            else:
                raise UserError(
                    'Tipo documento "%s" es inválido para una factura', tipo_documento
                )

        # Credit Note
        elif self.move_type == "out_refund":
            tipo_documento = "NC"
            if self.journal_id.NC_sequence_id:
                sequence = self.journal_id.NC_sequence_id.with_company(
                    self.company_id
                )._next()
            else:
                self.state_tributacion = "na"
                self.message_post(subject=_("Warning"), body=no_sequence_message)

        # Payment Receipt (REP)
        elif tipo_documento == "REP":
            if self.journal_id.REP_sequence_id:
                sequence = self.journal_id.REP_sequence_id.next_by_id()
            else:
                # Fallback or error?
                # If no sequence, we should probably warn or error.
                pass  # Will return False matching behavior of other types

        # Digital Supplier Invoice
        elif (
            self.move_type == "in_invoice"
            and self.partner_id.country_id
            and self.partner_id.country_id.code == "CR"
            and self.partner_id.identification_id
            and self.partner_id.vat
            and self.xml_supplier_approval is False
        ):
            tipo_documento = "FEC"
            if self.journal_id.FEC_sequence_id:
                sequence = self.journal_id.FEC_sequence_id.with_company(
                    self.company_id
                )._next()
            else:
                self.state_tributacion = "na"
                self.message_post(subject=_("Warning"), body=no_sequence_message)

        return (tipo_documento, sequence)

    # -------------------------------------------------------------------------
    # CRON
    # -------------------------------------------------------------------------

    @api.model
    def _check_hacienda_for_mrs(self, max_invoices=10):  # cron
        invoices = self.env["account.move"].search(
            [
                ("move_type", "in", ["in_invoice", "in_refund"]),
                ("tipo_documento", "!=", "FEC"),
                ("state", "=", "posted"),
                ("xml_supplier_approval", "!=", False),
                ("state_invoice_partner", "!=", False),
                (
                    "state_tributacion",
                    "not in",
                    ["aceptado", "rechazado", "error", "na"],
                ),
            ],
            limit=max_invoices,
        )
        total_invoices = len(invoices)
        current_invoice = 0

        for inv in invoices:
            # CWong: esto no debe llamarse porque cargaría de nuevo los impuestos y ya se pusieron como debería
            # if not i.amount_total_electronic_invoice:
            #     i.charge_xml_data()
            current_invoice += 1
            _logger.info(
                "_check_hacienda_for_mrs - Invoice %s / %s  -  number:%s"
                % (current_invoice, total_invoices, inv.number_electronic)
            )
            inv.send_mrs_to_hacienda()

    @api.model
    def _check_hacienda_for_invoices(self, max_invoices=10):
        out_invoices = self.env["account.move"].search(
            [
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
                (
                    "state_tributacion",
                    "in",
                    ["recibido", "procesando", "ne"],
                ),  # , 'error'
            ],
            limit=max_invoices,
        )

        in_invoices = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("tipo_documento", "=", "FEC"),
                ("state", "=", "posted"),
                ("state_tributacion", "in", ["procesando", "ne", "error"]),
            ],
            limit=max_invoices,
        )

        invoices = out_invoices | in_invoices

        total_invoices = len(invoices)
        current_invoice = 0

        _logger.info(
            _(f"E-INV CR - Inquiry Treasury - Invoices to Verify: {total_invoices}")
        )

        for i in invoices:
            try:
                current_invoice += 1
                _logger.info(
                    _("E-INV CR - Consult Hacienda - Invoice %s / %s  -  number:%s")
                    % (current_invoice, total_invoices, i.number_electronic)
                )

                token_m_h = api_facturae.get_token_hacienda(
                    i, i.company_id.frm_ws_ambiente
                )

                if not token_m_h:
                    _logger.error(
                        _("E-INV CR - Consult Hacienda - HALTED - Failed to get token")
                    )
                    return

                if not i.xml_comprobante:
                    i.state_tributacion = "error"
                    _logger.warning(
                        _("E-INV CR - Document:%s has no XML document. Status %s"),
                        i.number_electronic,
                        "error",
                    )
                    continue

                if not i.number_electronic or len(i.number_electronic) != 50:
                    i.state_tributacion = "error"
                    _logger.warning(
                        _("E-INV CR - Document:%s does not comply with the format of ")
                        + _("electronic number. Status: %s"),
                        i.number,
                        "error",
                    )
                    continue

                response_json = api_facturae.consulta_clave(
                    i.number_electronic, token_m_h, i.company_id.frm_ws_ambiente
                )
                status = response_json["status"]

                if status == 200:
                    estado_m_h = response_json.get("ind-estado")
                    _logger.info(_(f"E-INV CR - Document Status:{estado_m_h}"))
                elif status == 400:
                    estado_m_h = response_json.get("ind-estado")
                    i.state_tributacion = "ne"
                    _logger.warning(
                        _("E-INV CR - Document:%s not found in")
                        + _("Hacienda.  Status: %s"),
                        i.number_electronic,
                        estado_m_h,
                    )
                    continue
                else:
                    _logger.error(
                        _("E-INV CR - Unexpected error in query Hacienda  - Aborting")
                    )
                    return

                i.state_tributacion = estado_m_h

                if estado_m_h == "aceptado":
                    i.fname_xml_respuesta_tributacion = (
                        "AHC_" + i.number_electronic + ".xml"
                    )
                    attachment_resp = self.env["ir.attachment"].create(
                        {
                            "name": i.fname_xml_respuesta_tributacion,
                            "type": "binary",
                            "datas": response_json.get("respuesta-xml"),
                            "res_model": i._name,
                            "res_id": i.id,
                            "res_field": "xml_respuesta_tributacion",
                            "res_name": i.fname_xml_respuesta_tributacion,
                            "mimetype": "text/xml",
                        }
                    )

                    if (
                        i.tipo_documento != "FEC"
                        and i.partner_id
                        and i.partner_id.email
                    ):
                        email_template = self.env.ref(
                            "account.email_template_edi_invoice", False
                        )

                        # Lista para almacenar todos los attachments
                        attachment_ids = []

                        # 1. Generar PDF de la factura
                        try:
                            pdf_content, pdf_format = (
                                self.env["ir.actions.report"]
                                .sudo()
                                ._render("account.account_invoices", [i.id])
                            )
                            pdf_attachment = (
                                self.env["ir.attachment"]
                                .sudo()
                                .create(
                                    {
                                        "name": (
                                            f"{i.tipo_documento}_{i.number_electronic}.pdf"
                                            if i.tipo_documento
                                            else f"{i.name}.pdf"
                                        ),
                                        "type": "binary",
                                        "datas": base64.b64encode(pdf_content),
                                        "res_model": i._name,
                                        "res_id": i.id,
                                        "mimetype": "application/pdf",
                                    }
                                )
                            )
                            attachment_ids.append(pdf_attachment.id)
                        except Exception as e:
                            # Log del error pero no detener el proceso
                            _logger.warning(
                                f"Error generating PDF for invoice {i.name}: {str(e)}"
                            )

                        # 2. Buscar XML comprobante
                        domain = [
                            ("res_model", "=", i._name),
                            ("res_id", "=", i.id),
                            ("res_field", "=", "xml_comprobante"),
                        ]
                        attachment = (
                            self.env["ir.attachment"].sudo().search(domain, limit=1)
                        )

                        if attachment and attachment_resp:
                            # Agregar copias de los XMLs
                            attach_copy = attachment.copy()
                            attach_resp_copy = attachment_resp.copy()
                            attachment_ids.extend([attach_copy.id, attach_resp_copy.id])

                            # Asignar todos los attachments al template (PDF + XMLs)
                            email_template.attachment_ids = [(6, 0, attachment_ids)]

                            email_template.with_context(
                                type="binary", default_type="binary"
                            ).send_mail(i.id, raise_exception=False, force_send=True)

                            # Limpiar attachments del template
                            email_template.attachment_ids = [(5, 0, 0)]

                elif estado_m_h in ("firma_invalida"):
                    if i.error_count > 10:
                        i.fname_xml_respuesta_tributacion = (
                            "AHC_" + i.number_electronic + ".xml"
                        )
                        self.env["ir.attachment"].create(
                            {
                                "name": i.fname_xml_respuesta_tributacion,
                                "type": "binary",
                                "datas": response_json.get("respuesta-xml"),
                                "res_model": i._name,
                                "res_id": i.id,
                                "res_field": "xml_respuesta_tributacion",
                                "res_name": i.fname_xml_respuesta_tributacion,
                                "mimetype": "text/xml",
                            }
                        )
                        i.state_email = "fe_error"
                        _logger.info(_("email not sent - invoice rejected"))
                    else:
                        i.error_count += 1
                        i.state_tributacion = "procesando"

                elif estado_m_h == "rechazado":
                    i.state_email = "fe_error"
                    i.state_tributacion = estado_m_h
                    i.fname_xml_respuesta_tributacion = (
                        "AHC_" + i.number_electronic + ".xml"
                    )
                    self.env["ir.attachment"].create(
                        {
                            "name": i.fname_xml_respuesta_tributacion,
                            "type": "binary",
                            "datas": response_json.get("respuesta-xml"),
                            "res_model": self._name,
                            "res_id": i.id,
                            "res_field": "xml_respuesta_tributacion",
                            "res_name": i.fname_xml_respuesta_tributacion,
                            "mimetype": "text/xml",
                        }
                    )
                else:
                    if i.error_count > 10:
                        i.state_tributacion = "error"
                    elif i.error_count < 4:
                        i.error_count += 1
                        i.state_tributacion = "procesando"
                    else:
                        i.error_count += 1
                        i.state_tributacion = ""
                    # doc.state_tributacion = 'no_encontrado'
                    _logger.error(
                        "E-INV CR - Query Hacienda - Invoice not found: %s  - Hacienda Status: %s"
                        % (i.number_electronic, estado_m_h)
                    )
            except Exception as error:
                i.state_tributacion = "error"
                i.message_post(
                    subject=_("Error"),
                    body=_("Warning!.\n Error in _check_hacienda_for_invoices: ")
                    + str(error),
                )
                continue

    def send_mrs_to_hacienda(self):
        for inv in self:
            if inv.xml_supplier_approval:

                # Verificar si el MR ya fue enviado y estamos esperando la confirmación
                if inv.state_tributacion == "procesando":

                    token_m_h = api_facturae.get_token_hacienda(
                        inv, inv.company_id.frm_ws_ambiente
                    )

                    api_facturae.consulta_documentos(
                        inv,
                        inv,
                        inv.company_id.frm_ws_ambiente,
                        token_m_h,
                        api_facturae.get_time_hacienda(),
                        False,
                    )
                else:
                    if inv.state_tributacion and inv.state_tributacion in (
                        "aceptado",
                        "rechazado",
                        "na",
                    ):
                        raise UserError(
                            _(
                                "Warning!.\n The supplier invoice has already been confirmed"
                            )
                        )
                    if (
                        not inv.amount_total_electronic_invoice
                        and inv.xml_supplier_approval
                    ):
                        try:
                            inv.load_xml_data()
                        except UserError as error:
                            inv.state_tributacion = "error"
                            inv.message_post(
                                subject=_("Error"),
                                body=_("Aviso!.\n Error en carga del XML del proveedor")
                                + str(error),
                            )
                            continue
                    _logger.info(
                        'FECR - Total comparison: XML=%s, Odoo=%s, Diff=%s',
                        inv.amount_total_electronic_invoice,
                        inv.amount_total - (inv.amount_iva_returned or 0),
                        inv.amount_total_electronic_invoice - (inv.amount_total - (inv.amount_iva_returned or 0))
                    )
                    odoo_total = inv.amount_total - (inv.amount_iva_returned or 0)
                    if abs(inv.amount_total_electronic_invoice - odoo_total) > 1:
                        inv.state_tributacion = "error"
                        inv.message_post(
                            subject=_("Error"),
                            body=_(
                                "Warning!.\n Total amount does not match XML amount"
                            ),
                        )
                        continue

                    elif not inv.xml_supplier_approval:
                        inv.state_tributacion = "error"
                        inv.message_post(
                            subject=_("Error"),
                            body=_("Warning!.\n XML file not loaded"),
                        )
                        continue

                    elif (
                        not inv.company_id.sucursal_MR or not inv.company_id.terminal_MR
                    ):
                        inv.state_tributacion = "error"
                        inv.message_post(
                            subject=_("Error"),
                            body=_(
                                "Warning!.\n Please configure the purchase journal, terminal and branch"
                            ),
                        )
                        continue

                    if not inv.state_invoice_partner:
                        inv.state_tributacion = "error"
                        inv.message_post(
                            subject=_("Error"),
                            body=_(
                                "Warning!\nYou must first select the response type for the uploaded file."
                            ),
                        )
                        continue

                    if (
                        inv.company_id.frm_ws_ambiente != "disabled"
                        and inv.state_invoice_partner
                    ):
                        # '''Si por el contrario es un documento nuevo, asignamos todos los valores'''
                        if (
                            not inv.xml_comprobante
                            or inv.state_invoice_partner
                            not in ["procesando", "aceptado"]
                        ):

                            if inv.state_invoice_partner == "1":
                                detalle_mensaje = "Aceptado"
                                tipo = 1
                                tipo_documento = "CCE"
                                sequence_rec = inv.company_id.CCE_sequence_id
                                if not sequence_rec:
                                    inv.company_id.try_create_configuration_sequences()
                                    sequence_rec = inv.company_id.CCE_sequence_id
                                if not sequence_rec:
                                    raise UserError(_("No se encontró la secuencia para Aceptación (CCE) en la compañía %s. Por favor, asegúrese de que el nombre comercial y el nombre legal de la compañía estén configurados.") % inv.company_id.name)
                                sequence = sequence_rec.with_company(inv.company_id)._next()

                            elif inv.state_invoice_partner == "2":
                                detalle_mensaje = "Aceptado parcial"
                                tipo = 2
                                tipo_documento = "CPCE"
                                sequence_rec = inv.company_id.CPCE_sequence_id
                                if not sequence_rec:
                                    inv.company_id.try_create_configuration_sequences()
                                    sequence_rec = inv.company_id.CPCE_sequence_id
                                if not sequence_rec:
                                    raise UserError(_("No se encontró la secuencia para Aceptación Parcial (CPCE) en la compañía %s.") % inv.company_id.name)
                                sequence = sequence_rec.with_company(inv.company_id)._next()
                            else:
                                detalle_mensaje = "Rechazado"
                                tipo = 3
                                tipo_documento = "RCE"
                                sequence_rec = inv.company_id.RCE_sequence_id
                                if not sequence_rec:
                                    inv.company_id.try_create_configuration_sequences()
                                    sequence_rec = inv.company_id.RCE_sequence_id
                                if not sequence_rec:
                                    raise UserError(_("No se encontró la secuencia para Rechazo (RCE) en la compañía %s.") % inv.company_id.name)
                                sequence = sequence_rec.with_company(inv.company_id)._next()

                            # Si el mensaje fue rechazado, necesitamos generar un nuevo id
                            if inv.state_tributacion in ["rechazado", "error"]:
                                message_description = Markup("%s<br/>") % (
                                    _("Consecutive Switching of Receiver Message")
                                )
                                message_description = Markup("<ul>")
                                message_description += Markup("<li>%s %s</li>") % (
                                    _("Previous consecutive:"),
                                    inv.consecutive_number_receiver,
                                )
                                message_description += Markup("<li>%s %s</li>") % (
                                    _("Previous state: "),
                                    inv.state_tributacion,
                                )

                            # '''Solicitamos la clave para el Mensaje Receptor'''
                            response_json = api_facturae.get_clave_hacienda(
                                inv,
                                tipo_documento,
                                sequence,
                                inv.company_id.sucursal_MR,
                                inv.company_id.terminal_MR,
                            )

                            inv.consecutive_number_receiver = response_json.get(
                                "consecutivo"
                            )
                            # Generamos el Mensaje Receptor
                            if (
                                inv.amount_total_electronic_invoice is None
                                or inv.amount_total_electronic_invoice == 0
                            ):
                                inv.state_tributacion = "error"
                                inv.message_post(
                                    subject=_("Error"),
                                    body=_(
                                        "The Total amount of the Invoice for the Message Receiver is invalid"
                                    ),
                                )
                                continue

                            xml = api_facturae.gen_xml_mr_43(
                                inv.number_electronic,
                                inv.partner_id.vat,
                                inv.date_issuance,
                                tipo,
                                detalle_mensaje,
                                inv.company_id.vat,
                                inv.consecutive_number_receiver,
                                inv.amount_tax_electronic_invoice,
                                inv.amount_total_electronic_invoice,
                                inv.company_id.activity_id.code,
                                "01",
                            )

                            xml_firmado = api_facturae.sign_xml(
                                inv.company_id.signature, inv.company_id.frm_pin, xml
                            )

                            inv.fname_xml_comprobante = (
                                tipo_documento + "_" + inv.number_electronic + ".xml"
                            )
                            self.env["ir.attachment"].sudo().create(
                                {
                                    "name": inv.fname_xml_comprobante,
                                    "type": "binary",
                                    "datas": base64.b64encode(xml_firmado),
                                    "res_model": inv._name,
                                    "res_id": inv.id,
                                    "res_field": "xml_comprobante",
                                    "res_name": inv.fname_xml_comprobante,
                                    "mimetype": "text/xml",
                                }
                            )

                            inv.tipo_documento = tipo_documento

                            if inv.state_tributacion != "procesando":

                                env = inv.company_id.frm_ws_ambiente
                                token_m_h = api_facturae.get_token_hacienda(
                                    inv, inv.company_id.frm_ws_ambiente
                                )

                                response_json = api_facturae.send_message(
                                    inv,
                                    api_facturae.get_time_hacienda(),
                                    xml_firmado,
                                    token_m_h,
                                    env,
                                )
                                status = response_json.get("status")

                                if 200 <= status <= 299:
                                    inv.state_tributacion = "procesando"
                                else:
                                    inv.state_tributacion = "error"
                                    _logger.error(
                                        "E-INV CR - Invoice: %s  Error sending Acceptance Message: %s",
                                        inv.number_electronic,
                                        response_json.get("text"),
                                    )

                                if inv.state_tributacion == "procesando":
                                    token_m_h = api_facturae.get_token_hacienda(
                                        inv, inv.company_id.frm_ws_ambiente
                                    )

                                    if not token_m_h:
                                        _logger.error(
                                            _(
                                                "E-INV CR - Send Acceptance Message - HALTED - Failed to get token"
                                            )
                                        )
                                        return

                                    response_json = api_facturae.consulta_clave(
                                        inv.number_electronic
                                        + "-"
                                        + inv.consecutive_number_receiver,
                                        token_m_h,
                                        inv.company_id.frm_ws_ambiente,
                                    )
                                    status = response_json["status"]

                                    if status == 200:
                                        inv.state_tributacion = response_json.get(
                                            "ind-estado"
                                        )
                                        # inv.xml_respuesta_tributacion = response_json.get('respuesta-xml')
                                        n_elect = inv.number_electronic
                                        c_number = inv.consecutive_number_receiver
                                        inv.fname_xml_respuesta_tributacion = (
                                            "ACH_%s-%s.xml" % (n_elect, c_number)
                                        )
                                        # file_name used to avoid: E501 line too long
                                        file_name = inv.fname_xml_respuesta_tributacion
                                        self.env["ir.attachment"].create(
                                            {
                                                "name": file_name,
                                                "type": "binary",
                                                "datas": response_json.get(
                                                    "respuesta-xml"
                                                ),
                                                "res_model": self._name,
                                                "res_id": inv.id,
                                                "res_field": "xml_respuesta_tributacion",
                                                "res_name": file_name,
                                                "mimetype": "text/xml",
                                            }
                                        )

                                        _logger.error(
                                            "E-INV CR - Estado Documento:%s",
                                            inv.state_tributacion,
                                        )

                                        message_description = Markup(
                                            "<strong>%s</strong><br/>"
                                        ) % (
                                            _(
                                                "Se ha enviado satisfactoriamente un Mensaje de Receptor"
                                            )
                                        )
                                        message_description += Markup("<ul>")
                                        message_description += Markup(
                                            "<li>%s %s</li>"
                                        ) % (_("Documento: "), inv.number_electronic)
                                        message_description += Markup(
                                            "<li>%s %s</li>"
                                        ) % (
                                            _("Consecutivo de mensaje: "),
                                            inv.consecutive_number_receiver,
                                        )
                                        message_description += Markup(
                                            "<li>%s %s</li>"
                                        ) % (_("Detalle de mensaje: "), detalle_mensaje)
                                        message_description += Markup("</ul>")

                                        self.message_post(
                                            body=message_description,
                                            subtype_xmlid="mail.mt_comment",
                                        )

                                        _logger.info(
                                            _(
                                                f"E-INV CR - Document Status:{inv.state_tributacion}"
                                            )
                                        )

                                    elif status == 400:
                                        inv.state_tributacion = "ne"
                                        _logger.error(
                                            _(
                                                "E-INV CR - Document Acceptance:%s not found in Hacienda."
                                            ),
                                            inv.number_electronic
                                            + "-"
                                            + inv.consecutive_number_receiver,
                                        )
                                    else:
                                        _logger.error(
                                            _(
                                                "E-INV CR - Unexpected error in Send Acceptance File - Aborting"
                                            )
                                        )
                                        return

    @api.model
    def _send_invoices_to_hacienda(self, max_invoices=10):  # cron
        _logger.info("##### CRON - Envía Facturas a Hacienda")
        days_left = self.company_id.get_days_left()
        _logger.debug("E-INV CR - Ejecutando _send_invoices_to_hacienda")
        invoices = self.env["account.move"].search(
            [
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
                ("number_electronic", "!=", False),
                ("invoice_date", ">=", "2019-07-01"),
                "|",
                ("state_tributacion", "=", False),
                ("state_tributacion", "=", "ne"),
            ],
            order="id asc",
            limit=max_invoices,
        )

        print(invoices)

        if days_left >= 0:
            self.generate_and_send_invoices(invoices)
        else:
            message = self.company_id.get_message_to_send()
            for inv in invoices:
                inv.message_post(
                    body=message,
                    subject=_("IMPORTANT NOTICE!!"),
                    message_type="notification",
                    # subtype=None,
                    parent_id=False,
                )
                inv.state_tributacion = "error"
        _logger.info("E-INV CR - _send_invoices_to_hacienda - Completed Successfully")

    # -------------------------------------------------------------------------
    # PUBLIC ACTIONS
    # -------------------------------------------------------------------------

    def action_send_mrs_to_hacienda(self):
        if self.state_invoice_partner:
            self.state_tributacion = False
            self.send_mrs_to_hacienda()
        else:
            raise UserError(
                _(
                    "You must select the aceptance state: Accepted, Parcial Accepted or Rejected"
                )
            )

    def action_check_hacienda(self):
        if self.company_id.frm_ws_ambiente != "disabled":
            for inv in self:
                token_m_h = api_facturae.get_token_hacienda(
                    inv, inv.company_id.frm_ws_ambiente
                )
                api_facturae.consulta_documentos(
                    self, inv, self.company_id.frm_ws_ambiente, token_m_h, False, False
                )

    def action_check_hacienda_for_invoices(self):
        self._check_hacienda_for_invoices()

    def action_create_fec(self):
        if self.company_id.frm_ws_ambiente == "disabled":
            raise UserError(_("Hacienda API is disabled in company"))
        else:
            self.generate_and_send_invoices(self)

    def generate_and_send_invoice(self):
        days_left = self.company_id.get_days_left()
        if days_left >= 0:
            self.generate_and_send_invoices(self)
        else:
            message = self.company_id.get_message_to_send()
            self.message_post(
                body=message,
                subject=_("IMPORTANT NOTICE!!"),
                message_type="notification",
                # subtype=None,
                parent_id=False,
            )
        _logger.info("E-INV CR - _send_invoices_to_hacienda - Completed Successfully")

    def generate_and_send_invoices(self, invoices):
        def cleanhtml(raw_html):
            CLEANR = re.compile("<.*?>")
            cleantext = re.sub(CLEANR, "", raw_html)
            return cleantext

        total_invoices = len(invoices)
        current_invoice = 0

        days_left = self.company_id.get_days_left()
        message = self.company_id.get_message_to_send()
        for inv in invoices:
            try:
                current_invoice += 1

                if days_left <= self.company_id.range_days:
                    inv.message_post(
                        body=message,
                        subject=_("IMPORTANT NOTICE!!"),
                        message_type="notification",
                        # subtype=None,
                        parent_id=False,
                    )

                if not inv.sequence or not inv.sequence.isdigit():
                    inv.state_tributacion = "na"
                    _logger.info("E-INV CR - Ignored invoice:%s", inv.number_electronic)
                    continue

                _logger.debug(
                    "generate_and_send_invoices - Invoice %s / %s  -  number:%s"
                    % (current_invoice, total_invoices, inv.number_electronic)
                )

                if not inv.xml_comprobante or (
                    inv.tipo_documento == "FEC" and inv.state_tributacion == "rechazado"
                ):
                    if (
                        inv.tipo_documento == "FEC"
                        and inv.state_tributacion == "rechazado"
                    ):
                        msg_body = _(
                            "Another FEC is being sent because the previous one was rejected by Hacienda. "
                        )
                        msg_body += _("Attached the previous XMLs. Previous key: ")
                        fname_xml_respuesta_tributacion = (
                            inv.fname_xml_respuesta_tributacion.copy()
                        )
                        fname_xml_comprobante = inv.fname_xml_comprobante.copy()
                        inv.message_post(
                            body=msg_body + inv.number_electronic,
                            subject=_("Sending a second FEC"),
                            message_type="notification",
                            # subtype=None,
                            parent_id=False,
                            attachments=[
                                [
                                    fname_xml_respuesta_tributacion,
                                    fname_xml_respuesta_tributacion,
                                ],
                                [fname_xml_comprobante, fname_xml_comprobante],
                            ],
                        )

                        sequence = inv.company_id.FEC_sequence_id.with_company(
                            self.company_id
                        )._next()
                        response_json = api_facturae.get_clave_hacienda(
                            self,
                            inv.tipo_documento,
                            sequence,
                            inv.journal_id.sucursal,
                            inv.journal_id.terminal,
                        )

                        inv.number_electronic = response_json.get("clave")
                        inv.sequence = response_json.get("consecutivo")

                    now_utc = datetime.datetime.now(pytz.timezone("UTC"))
                    now_cr = now_utc.astimezone(pytz.timezone("America/Costa_Rica"))
                    dia = inv.number_electronic[3:5]  # '%02d' % now_cr.day,
                    mes = inv.number_electronic[5:7]  # '%02d' % now_cr.month,
                    anno = inv.number_electronic[7:9]  # str(now_cr.year)[2:4],
                    date_cr = now_cr.strftime(
                        "20" + anno + "-" + mes + "-" + dia + "T%H:%M:%S-06:00"
                    )
                    inv.date_issuance = date_cr
                    numero_documento_referencia = False
                    fecha_emision_referencia = False
                    codigo_referencia = False
                    tipo_documento_referencia = False
                    razon_referencia = False
                    currency = inv.currency_id
                    invoice_comments = (
                        escape(cleanhtml(inv.narration)) if inv.narration else ""
                    )
                    reference_code_id = inv.reference_code_id
                    if (
                        (inv.invoice_id or inv.not_loaded_invoice)
                        and reference_code_id
                        and inv.reference_document_id
                    ):
                        if inv.invoice_id:
                            if (
                                inv.invoice_id.number_electronic
                                and inv.invoice_line_ids[0].product_id
                            ):
                                numero_documento_referencia = (
                                    inv.invoice_id.number_electronic
                                )
                                fecha_emision_referencia = (
                                    inv.invoice_id.date_issuance
                                    or inv.invoice_id.invoice_date.strftime("%Y-%m-%d")
                                    + "T12:00:00-06:00"
                                )
                            else:
                                numero_documento_referencia = (
                                    inv.invoice_id
                                    and re.sub("[^0-9]+", "", inv.invoice_id.sequence)
                                    or re.sub("[^0-9]+", "", inv.invoice_id.name)
                                )
                                invoice_date = inv.invoice_id.invoice_date
                                fecha_emision_referencia = (
                                    invoice_date.strftime("%Y-%m-%d")
                                    + "T12:00:00-06:00"
                                )
                        else:
                            numero_documento_referencia = inv.not_loaded_invoice
                            fecha_emision_referencia = (
                                inv.not_loaded_invoice_date.strftime("%Y-%m-%d")
                            )
                            fecha_emision_referencia += "T12:00:00-06:00"
                        tipo_documento_referencia = inv.reference_document_id.code
                        codigo_referencia = inv.reference_code_id.code
                        razon_referencia = inv.reference_code_id.name
                    elif inv.tipo_documento == "FEC" and inv.reference_document_id.code:
                        tipo_documento_referencia = inv.reference_document_id.code
                        numero_documento_referencia = inv.number_electronic
                        fecha_emision_referencia = inv.date_issuance
                        codigo_referencia = "04"  # Referencia a otro documento
                        razon_referencia = inv.reference_document_id.name

                    if inv.invoice_payment_term_id:
                        sale_conditions = (
                            inv.invoice_payment_term_id.sale_conditions_id
                            and inv.invoice_payment_term_id.sale_conditions_id.code
                            or "01"
                        )
                    else:
                        sale_conditions = "01"

                    # Validate if invoice currency is the same as the company currency
                    if currency.name == self.company_id.currency_id.name:
                        currency_rate = 1
                    elif (
                        inv.tipo_documento == "NC"
                        and currency.name != self.company_id.currency_id.name
                    ):
                        Original_Currency = (
                            inv.invoice_id.amount_total_signed
                            / inv.invoice_id.amount_total_in_currency_signed
                        )
                        currency_rate = round(Original_Currency, 5)
                    else:
                        currency_rate = round(1.0 / currency.rate, 5)

                    # Generamos las líneas de la factura
                    lines = dict([])
                    otros_cargos = dict([])
                    otros_cargos_id = 0
                    line_number = 0
                    tax_regalia = 0.0
                    total_otros_cargos = 0.0
                    total_iva_devuelto = 0.0
                    total_servicio_salon = 0.0
                    total_servicio_gravado = 0.0
                    total_servicio_no_sujeto = 0.0
                    total_servicio_exento = 0.0
                    total_servicio_exonerado = 0.0
                    total_mercaderia_gravado = 0.0
                    total_mercaderia_no_sujeto = 0.0
                    total_mercaderia_exento = 0.0
                    total_mercaderia_exonerado = 0.0
                    total_desgloce_impuesto = dict([])
                    total_descuento = 0.0
                    total_impuestos_asum_emisor_fabrica = (
                        0.0  # TotalImpAsumEmisorFabrica
                    )
                    total_impuestos = 0.0
                    base_subtotal = 0.0
                    _no_cabys_code = False

                    for inv_line in inv.invoice_line_ids.filtered(
                        lambda x: x.display_type == "product" and x.product_id
                    ):
                        # Revisamos si está línea es de Otros Cargos
                        env_iva_returned = (
                            self.env["product.product"]
                            .search([("name", "=", "IVA Devuelto")], limit=1)
                            .id
                        )
                        if (
                            inv_line.product_id
                            and inv_line.product_id.id == env_iva_returned
                        ):
                            total_iva_devuelto = -inv_line.price_total

                        elif (
                            inv_line.product_id
                            and inv_line.product_id.categ_id.name == "Otros Cargos"
                        ):
                            otros_cargos_id += 1
                            otros_cargos[otros_cargos_id] = {
                                "TipoDocumento": inv_line.product_id.default_code,
                                "Detalle": escape(inv_line.name[:150]),
                                "MontoCargo": inv_line.price_total,
                            }
                            if inv_line.third_party_id:
                                otros_cargos[otros_cargos_id][
                                    "NombreTercero"
                                ] = inv_line.third_party_id.name
                                if inv_line.third_party_id.vat:
                                    otros_cargos[otros_cargos_id][
                                        "NumeroIdentidadTercero"
                                    ] = inv_line.third_party_id.vat

                            total_otros_cargos += inv_line.price_total

                        else:
                            line_number += 1
                            price = inv_line.price_unit
                            quantity = inv_line.quantity
                            if not quantity:
                                continue

                            line_taxes = inv_line.tax_ids.compute_all(
                                price,
                                currency,
                                1,
                                product=inv_line.product_id,
                                partner=inv_line.move_id.partner_id,
                            )

                            price_unit = round(line_taxes["total_excluded"], 5)

                            base_line = round(price_unit * quantity, 5)
                            
                            # Identificamos si la línea es una regalía o bonificación
                            is_regalia = inv_line.discount_code_id and inv_line.discount_code_id.code in ["01", "03"]
                            line_tax_regalia = 0.0
                            
                            descuento = (
                                inv_line.discount
                                and round(
                                    price_unit * quantity * inv_line.discount / 100.0, 5
                                )
                                or 0.0
                            )
                            subtotal_line = round(base_line - descuento, 5)

                            # Corregir error cuando un producto trae en el nombre "", por ejemplo: "disco duro"
                            # Esto no debería suceder, pero, si sucede, lo corregimos
                            if inv_line.name[:156].find('"'):
                                detalle_linea = inv_line.name[:160].replace('"', "")

                            line = {
                                "cantidad": quantity,
                                "detalle": escape(detalle_linea),
                                "precioUnitario": price_unit,
                                "montoTotal": base_line,
                                "subtotal": subtotal_line,
                                "BaseImponible": subtotal_line,
                                "unidadMedida": inv_line.product_uom_id
                                and inv_line.product_uom_id.code
                                or "Sp",
                            }

                            if inv_line.product_id:
                                line["codigo"] = inv_line.product_id.default_code or ""
                                line["codigoProducto"] = inv_line.product_id.code or ""
                                partner_id = inv_line.move_id.partner_id
                                if len(partner_id.allowed_cabys_ids) != 0:
                                    allowed_codes = [
                                        code.name
                                        for code in partner_id.allowed_cabys_ids
                                    ]
                                else:
                                    cabys_codes = (
                                        self.env["cabys.producto"].sudo().search([])
                                    )
                                    allowed_codes = [
                                        code.codigo for code in cabys_codes
                                    ]
                                _logger.info(
                                    _("Checking CABYS code: %s")
                                    % inv_line.product_id.cabys_code
                                )
                                
                                # ══════════════════════════════════════════════════════════════
                                # Verificar si el CABYS está autorizado para exoneración
                                # Si NO está autorizado, la línea se procesa con IVA normal
                                # ══════════════════════════════════════════════════════════════
                                _cabys_not_authorized = False
                                if (
                                    partner_id.has_exoneration
                                    and inv_line.product_id.cabys_code
                                    and inv_line.product_id.cabys_code not in allowed_codes
                                ):
                                    _cabys_not_authorized = True
                                    _logger.info(
                                        "CABYS %s no autorizado para exoneración, línea se procesa con IVA normal",
                                        inv_line.product_id.cabys_code
                                    )
                                
                                # Asignar código CABYS
                                if inv_line.product_id.cabys_code:
                                    line["codigoCabys"] = inv_line.product_id.cabys_code
                                elif (
                                    inv_line.product_id.categ_id
                                    and inv_line.product_id.categ_id.cabys_code
                                ):
                                    line["codigoCabys"] = (
                                        inv_line.product_id.categ_id.cabys_code
                                    )
                                else:
                                    _no_cabys_code = _(
                                        f"Warning!.\nLine without CABYS code: {inv_line.name}"
                                    )
                                    continue
                            else:
                                _no_cabys_code = _(
                                    f"Warning!.\nLine without CABYS code: {inv_line.name}"
                                )
                                continue

                            # Validación: Deberá incluir al menos 12 dígitos cuando se
                            # trate de una FEE, NC o ND que modifiquen una FEE y que el
                            # primer digito del código CABYS sea 0, 1, 2, 3 y 4 (bienes).
                            if (
                                inv.tipo_documento == "FEE"
                                and inv_line.tariff_head
                                and inv_line.product_id.cabys_product_id.cabys_categoria1_id.codigo
                                in ["0", "1", "2", "3", "4"]
                            ):
                                line["partidaArancelaria"] = inv_line.tariff_head

                            if inv_line.discount and price_unit > 0:
                                total_descuento += descuento
                                line["montoDescuento"] = descuento
                                if inv_line.discount_code_id:
                                    line["codigoDescuento"] = (
                                        inv_line.discount_code_id.code
                                    )
                                    if inv_line.discount_code_id.code == "99":
                                        line["codigoDescuentoOTRO"] = (
                                            inv_line.discount_note
                                        )
                                    line["naturalezaDescuento"] = (
                                        inv_line.discount_code_id.display_name
                                    )
                                else:
                                    raise UserError(
                                        _(
                                            "The discount code is required when apply a discount."
                                        )
                                    )
                            # Se generan los impuestos
                            taxes = dict([])
                            _line_tax = 0.0
                            _tax_exoneration = False
                            _percentage_exoneration = 0
                            
                            # ══════════════════════════════════════════════════════════
                            # NUEVO: Detectar exoneración del partner para esta línea
                            # ══════════════════════════════════════════════════════════
                            _partner_exoneration_amount = 0.0
                            _partner_exoneration_pct = 0
                            _partner_exoneration = False
                            
                            
                            partner = inv_line.move_id.partner_id
                            # Solo aplicar exoneración si el CABYS está autorizado
                            if partner and partner.has_exoneration and partner.percentage_exoneration > 0 and not _cabys_not_authorized:
                                _partner_exoneration = True
                                if not partner.date_expiration or partner.date_expiration >= datetime.date.today():
                                    _partner_exoneration_pct = partner.percentage_exoneration
                            
                            if inv_line.tax_ids:
                                tax_index = 0

                                taxes_lookup = {}
                                for i in inv_line.tax_ids:
                                    # ══════════════════════════════════════════════════════════
                                    # NUEVO: Verificar si el PARTNER tiene exoneración
                                    # (además de la exoneración del impuesto)
                                    # ══════════════════════════════════════════════════════════
                                    if partner.has_exoneration and not _cabys_not_authorized:
                                        _tax_exoneration = True
                                        _tax_rate = i.amount
                                        _tax_exoneration_rate = min(
                                            partner.percentage_exoneration, _tax_rate
                                        )
                                        _percentage_exoneration = (
                                            _tax_exoneration_rate / _tax_rate
                                        )
                                        taxes_lookup[i.id] = {
                                            "tax_code": i.tax_code,
                                            "tarifa": _tax_rate,
                                            "iva_tax_desc": i.iva_tax_desc,
                                            "iva_tax_code": i.iva_tax_code,
                                            "exoneration_percentage": _tax_exoneration_rate,
                                            "amount_exoneration": i.amount,
                                        }
                                    elif _partner_exoneration_pct > 0 and i.tax_code in ['01', '04'] and not _cabys_not_authorized:
                                        # ══════════════════════════════════════════════════════════
                                        # NUEVO: Exoneración del PARTNER para IVA
                                        # ══════════════════════════════════════════════════════════
                                        _tax_exoneration = True
                                        _tax_rate = i.amount
                                        _tax_exoneration_rate = min(_partner_exoneration_pct, _tax_rate)
                                        _percentage_exoneration = _tax_exoneration_rate / _tax_rate if _tax_rate > 0 else 0
                                        taxes_lookup[i.id] = {
                                            "tax_code": i.tax_code,
                                            "tarifa": _tax_rate,
                                            "iva_tax_desc": i.iva_tax_desc,
                                            "iva_tax_code": i.iva_tax_code,
                                            "exoneration_percentage": _tax_exoneration_rate,
                                            "amount_exoneration": _tax_exoneration_rate,  # Para partner-based
                                            "partner_exoneration": True,  # Flag para identificar origen
                                        }
                                    else:
                                        taxes_lookup[i.id] = {
                                            "tax_code": i.tax_code,
                                            "tarifa": i.amount,
                                            "iva_tax_desc": i.iva_tax_desc,
                                            "iva_tax_code": i.iva_tax_code,
                                        }

                                for i in line_taxes["taxes"]:
                                    if taxes_lookup[i["id"]]["tax_code"] == "service":
                                        total_servicio_salon += round(
                                            subtotal_line
                                            * taxes_lookup[i["id"]]["tarifa"]
                                            / 100,
                                            5,
                                        )

                                    elif taxes_lookup[i["id"]]["tax_code"] != "00":
                                        tax_index += 1
                                        
                                        # Base para el impuesto: MontoTotal si es regalía, sino SubTotal
                                        base_for_tax = base_line if is_regalia else subtotal_line
                                        tax_amount = round(
                                            base_for_tax
                                            * taxes_lookup[i["id"]]["tarifa"]
                                            / 100,
                                            5,
                                        )

                                        tax = {
                                            "codigo": taxes_lookup[i["id"]]["tax_code"],
                                            "tarifa": taxes_lookup[i["id"]]["tarifa"],
                                            "monto": tax_amount,
                                            "iva_tax_desc": taxes_lookup[i["id"]][
                                                "iva_tax_desc"
                                            ],
                                            "iva_tax_code": taxes_lookup[i["id"]][
                                                "iva_tax_code"
                                            ],
                                        }
                                        
                                        if is_regalia:
                                            tax["taxRegalia"] = tax_amount
                                            line_tax_regalia += tax_amount
                                            total_impuestos_asum_emisor_fabrica += tax_amount
                                            # No sumamos a _line_tax porque el impuesto neto es 0 y es asumido por el emisor
                                        else:
                                            _line_tax += tax_amount
                                            
                                            # ══════════════════════════════════════════════════════════
                                            # Se agrupan los impuestos segun el codigo para obtener 
                                            # el TotalDesgloceImpuesto (CON exoneración aplicada)
                                            # ══════════════════════════════════════════════════════════
                                            
                                            # Se genera la exoneración si existe para este impuesto
                                            if _tax_exoneration:
                                                exoneration_percentage = taxes_lookup[
                                                    i["id"]
                                                ]["exoneration_percentage"]
                                                _tax_amount_exoneration = round(
                                                    subtotal_line
                                                    * exoneration_percentage
                                                    / 100,
                                                    5,
                                                )

                                                _line_tax -= _tax_amount_exoneration

                                                tax["exoneracion"] = {
                                                    "montoImpuesto": _tax_amount_exoneration,
                                                    "porcentajeCompra": int(
                                                        exoneration_percentage
                                                    ),
                                                }
                                                
                                                net_tax = tax_amount - _tax_amount_exoneration
                                                
                                                if tax["codigo"] in total_desgloce_impuesto:
                                                    if (
                                                        tax["iva_tax_code"]
                                                        in total_desgloce_impuesto[
                                                            tax["codigo"]
                                                        ]
                                                    ):
                                                        total_desgloce_impuesto[
                                                            tax["codigo"]
                                                        ][tax["iva_tax_code"]] += round(
                                                            net_tax, 5
                                                        )
                                                    else:
                                                        total_desgloce_impuesto[
                                                            tax["codigo"]
                                                        ][tax["iva_tax_code"]] = round(
                                                            net_tax, 5
                                                        )
                                                else:
                                                    total_desgloce_impuesto[
                                                        tax["codigo"]
                                                    ] = {
                                                        tax["iva_tax_code"]: round(
                                                            net_tax, 5
                                                        )
                                                    }
                                            else:
                                                # Sin exoneración: incluir impuesto completo en desglose
                                                if tax["codigo"] in total_desgloce_impuesto:
                                                    if (
                                                        tax["iva_tax_code"]
                                                        in total_desgloce_impuesto[
                                                            tax["codigo"]
                                                        ]
                                                    ):
                                                        total_desgloce_impuesto[
                                                            tax["codigo"]
                                                        ][tax["iva_tax_code"]] += round(
                                                            tax["monto"], 5
                                                        )
                                                    else:
                                                        total_desgloce_impuesto[
                                                            tax["codigo"]
                                                        ][tax["iva_tax_code"]] = round(
                                                            tax["monto"], 5
                                                        )
                                                else:
                                                    total_desgloce_impuesto[
                                                        tax["codigo"]
                                                    ] = {
                                                        tax["iva_tax_code"]: round(
                                                            tax["monto"], 5
                                                        )
                                                    }

                                        taxes[tax_index] = tax

                                if is_regalia:
                                    line["taxRegalia"] = line_tax_regalia
                                elif (
                                        taxes.get(1)
                                        and taxes[1]["monto"] == 0
                                        and not is_regalia
                                    ):
                                        total_servicio_exento += base_line

                                line["impuesto"] = taxes
                                line["impuestoNeto"] = round(_line_tax, 5)

                            # ═══════════════════════════════════════════════════════════════════════════════
                            # CÁLCULO DE TOTALES PARA RESUMEN (FE v4.4)
                            # ═══════════════════════════════════════════════════════════════════════════════

                            # Servicios (CABYS categorías 5,6,7,8,9)
                            if (
                                inv_line.product_id.type == "service"
                                or inv_line.product_id.cabys_product_id.cabys_categoria1_id.codigo
                                in ["5", "6", "7", "8", "9"]
                            ):
                                if taxes:
                                    if _partner_exoneration:
                                        # Parte gravada (si no es exoneración 100%)
                                        if _percentage_exoneration < 1:
                                            total_servicio_gravado += base_line * (1 - _percentage_exoneration)
                                        # Parte exonerada
                                        total_servicio_exonerado += base_line * _percentage_exoneration
                                    elif (
                                        taxes.get(1)
                                        and taxes[1]["monto"] == 0
                                        and not inv_line["discount_code_id"].code
                                        in ["01", "03"]
                                    ):
                                        total_servicio_exento += base_line
                                    else:
                                        total_servicio_gravado += base_line
                                    total_impuestos += _line_tax
                                else:
                                    total_servicio_exento += base_line

                            # Mercancías (CABYS categorías 0,1,2,3,4)
                            elif (
                                inv_line.product_id.cabys_product_id.cabys_categoria1_id.codigo
                                in ["0", "1", "2", "3", "4"]
                            ):
                                if taxes:
                                    if _partner_exoneration:
                                        # Parte gravada (si no es exoneración 100%)
                                        if _percentage_exoneration < 1:
                                            total_mercaderia_gravado += base_line * (1 - _percentage_exoneration)
                                        # Parte exonerada
                                        total_mercaderia_exonerado += base_line * _percentage_exoneration
                                    elif taxes.get(1) and taxes[1]["monto"] == 0 and not is_regalia:
                                        total_mercaderia_exento += base_line
                                    else:
                                        total_mercaderia_gravado += base_line
                                    total_impuestos += _line_tax
                                else:
                                    total_mercaderia_exento += base_line

                            base_subtotal += subtotal_line
                            line["montoTotalLinea"] = round(subtotal_line + _line_tax, 5)
                            lines[line_number] = line


                    if total_servicio_salon:
                        total_servicio_salon = round(total_servicio_salon, 5)
                        total_otros_cargos += total_servicio_salon
                        otros_cargos_id += 1
                        otros_cargos[otros_cargos_id] = {
                            "TipoDocumento": "06",
                            "Detalle": escape("Servicio salon 10%"),
                            "MontoCargo": total_servicio_salon,
                        }

                    # Validar exoneración vigente antes de generar el XML
                    if inv.partner_id.has_exoneration:
                        # Verificar que la exoneración esté completa
                        if not inv.partner_id.type_exoneration:
                            inv.state_tributacion = "error"
                            inv.message_post(
                                subject=_("Error"), 
                                body=_("Falta especificar el tipo de documento de exoneración.")
                            )
                            continue
                        
                        if not inv.partner_id.exoneration_number:
                            inv.state_tributacion = "error"
                            inv.message_post(
                                subject=_("Error"), 
                                body=_("Falta especificar el número de documento de exoneración.")
                            )
                            continue
                        
                        if not inv.partner_id.institution_id and not inv.partner_id.institution_name:
                            inv.state_tributacion = "error"
                            inv.message_post(
                                subject=_("Error"), 
                                body=_("Falta especificar la institución emisora de la exoneración.")
                            )
                            continue
                        
                        if not inv.partner_id.date_issue:
                            inv.state_tributacion = "error"
                            inv.message_post(
                                subject=_("Error"), 
                                body=_("Falta especificar la fecha de emisión del documento de exoneración.")
                            )
                            continue
                        
                        # Verificar que la exoneración no esté vencida
                        if inv.partner_id.date_expiration:
                            if inv.partner_id.date_expiration < datetime.date.today():
                                raise UserError(_("La exoneración de este cliente ha vencido."))
                        
                        # Verificar campos obligatorios según el tipo de documento
                        if inv.partner_id.type_exoneration.code in ('02', '03', '06', '07', '08'):
                            if not inv.partner_id.exoneration_article:
                                inv.state_tributacion = "error"
                                inv.message_post(
                                    subject=_("Error"), 
                                    body=_("El número de artículo es obligatorio para este tipo de exoneración (códigos 02, 03, 06, 07, 08).")
                                )
                                continue
                        
                        # Verificar campo OTRO si tipo = 99
                        if inv.partner_id.type_exoneration.code == '99':
                            if not inv.partner_id.type_exoneration_other:
                                inv.state_tributacion = "error"
                                inv.message_post(
                                    subject=_("Error"), 
                                    body=_("El tipo de documento OTRO es obligatorio cuando se selecciona código 99.")
                                )
                                continue
                        
                        # Verificar campo OTRO si institución = 99
                        if inv.partner_id.institution_id and inv.partner_id.institution_id.code == '99':
                            if not inv.partner_id.institution_name_other:
                                inv.state_tributacion = "error"
                                inv.message_post(
                                    subject=_("Error"), 
                                    body=_("El nombre de institución OTRO es obligatorio cuando se selecciona código 99.")
                                )
                                continue
                    
                    # GUARDA EN LA REFERENCIA DE LA NC CUANDO SE CREA MANUALMENTE
                    if inv.invoice_id and not inv.invoice_origin:
                        inv.invoice_origin = inv.invoice_id.display_name

                    if (
                        _no_cabys_code and inv.tipo_documento != "NC"
                    ):  # CAByS is not required for financial NCs
                        inv.state_tributacion = "error"
                        inv.message_post(subject=_("Error"), body=_no_cabys_code)
                        continue

                    # ==================================================================================
                    # CALCULAR TOTAL DE EXONERACIONES PARA AJUSTAR LA VALIDACIÓN
                    # ==================================================================================
                    # Cuando hay exoneración, inv.amount_total incluye el IVA completo,
                    # pero total_impuestos es el IVA neto después de exoneración.
                    # La diferencia es el monto exonerado que debemos considerar.
                    # ==================================================================================

                    total_exonerado = 0.0
                    
                    for l in lines:
                        if "impuesto" in lines[l]:
                            for tax_key in lines[l]["impuesto"]:
                                tax_info = lines[l]["impuesto"][tax_key]
                                if "exoneracion" in tax_info:
                                    total_exonerado += tax_info["exoneracion"].get("montoImpuesto", 0)

                    total_exonerado = round(total_exonerado, 5)

                    # Validación de montos ajustada para exoneración
                    document_abs = base_subtotal + total_impuestos + total_otros_cargos
                    _logger.info("******************** ABS 1 %s" % document_abs)
                    document_abs = document_abs - total_iva_devuelto - inv.amount_total
                    _logger.info("******************** ABS 2 %s" % document_abs)
                    _logger.info("******************** Total Exonerado: %s" % total_exonerado)
                    _logger.info("******************** LINEAS\n%s" % lines)

                    if abs(document_abs) > 0.5:
                        inv.state_tributacion = "error"
                        body_message = _(
                            "Invoice amount does not match amount for XML. "
                        )
                        body_message += _(
                            "Invoice: %s XML:%s base:%s VAT:%s exonerated:%s otros_cargos:%s iva_returned:%s"
                        ) % (
                            inv.amount_total,
                            base_subtotal + total_impuestos + total_exonerado,
                            base_subtotal,
                            total_impuestos,
                            total_exonerado,
                            total_otros_cargos,
                            total_iva_devuelto,
                        )
                        inv.message_post(subject=_("Error"), body=body_message)
                        continue

                    total_servicio_gravado = round(total_servicio_gravado, 5)
                    total_servicio_exento = round(total_servicio_exento, 5)
                    total_servicio_exonerado = round(total_servicio_exonerado, 5)
                    total_mercaderia_gravado = round(total_mercaderia_gravado, 5)
                    total_mercaderia_exento = round(total_mercaderia_exento, 5)
                    total_mercaderia_exonerado = round(total_mercaderia_exonerado, 5)
                    total_otros_cargos = round(total_otros_cargos, 5)
                    total_iva_devuelto = round(total_iva_devuelto, 5)
                    base_subtotal = round(base_subtotal, 5)
                    total_impuestos_asum_emisor_fabrica = round(
                        total_impuestos_asum_emisor_fabrica, 5
                    )
                    
                    total_impuestos = round(total_impuestos, 5)
                    total_descuento = round(total_descuento, 5)
                    # ESTE METODO GENERA EL XML DIRECTAMENTE DESDE PYTHON
                    xml_string_builder = api_facturae.gen_xml_v44(
                        inv,
                        sale_conditions,
                        total_servicio_gravado,
                        total_servicio_exento,
                        total_servicio_no_sujeto,
                        total_servicio_exonerado,
                        total_mercaderia_gravado,
                        total_mercaderia_exento,
                        total_mercaderia_exonerado,
                        total_mercaderia_no_sujeto,
                        total_otros_cargos,
                        total_iva_devuelto,
                        base_subtotal,
                        total_impuestos_asum_emisor_fabrica,
                        total_impuestos,
                        total_desgloce_impuesto,
                        total_descuento,
                        lines,
                        otros_cargos,
                        currency_rate,
                        invoice_comments,
                        tipo_documento_referencia,
                        numero_documento_referencia,
                        fecha_emision_referencia,
                        codigo_referencia,
                        razon_referencia
                    )

                    xml_to_sign = str(xml_string_builder)
                    xml_firmado = api_facturae.sign_xml(
                        inv.company_id.signature, inv.company_id.frm_pin, xml_to_sign
                    )

                    # inv.xml_comprobante = base64.b64encode(xml_firmado)
                    inv.fname_xml_comprobante = (
                        inv.tipo_documento + "_" + inv.number_electronic + ".xml"
                    )
                    self.env["ir.attachment"].sudo().create(
                        {
                            "name": inv.fname_xml_comprobante,
                            "type": "binary",
                            "datas": base64.b64encode(xml_firmado),
                            "res_model": self._name,
                            "res_id": inv.id,
                            "res_field": "xml_comprobante",
                            "res_name": inv.fname_xml_comprobante,
                            "mimetype": "text/xml",
                        }
                    )

                    _logger.info("E-INV CR - SIGNED XML:%s", inv.fname_xml_comprobante)
                else:
                    xml_firmado = inv.xml_comprobante

                # Get token from Hacienda
                token_m_h = api_facturae.get_token_hacienda(
                    inv, inv.company_id.frm_ws_ambiente
                )

                response_json = api_facturae.send_xml_fe(
                    inv,
                    token_m_h,
                    inv.date_issuance,
                    xml_firmado,
                    inv.company_id.frm_ws_ambiente,
                )

                response_status = response_json.get("status")
                response_text = response_json.get("text")

                if 200 <= response_status <= 299:
                    if inv.tipo_documento == "FEC":
                        inv.state_tributacion = "procesando"
                    else:
                        inv.state_tributacion = "procesando"
                    inv.electronic_invoice_return_message = response_text
                else:
                    if response_text.find("ya fue recibido anteriormente") != -1:
                        if inv.tipo_documento == "FEC":
                            inv.state_tributacion = "procesando"
                        else:
                            inv.state_tributacion = "procesando"
                        inv.message_post(
                            subject=_("Error"),
                            body=_(
                                "Already received previously, it is passed to consult"
                            ),
                        )
                    elif inv.error_count > 10:
                        inv.message_post(subject=_("Error"), body=response_text)
                        inv.electronic_invoice_return_message = response_text
                        inv.state_tributacion = "error"
                        _logger.error(
                            _(
                                "E-INV CR  - Invoice: %s  Status: %s Error sending XML: %s"
                                % (
                                    inv.number_electronic,
                                    response_status,
                                    response_text,
                                )
                            )
                        )
                    else:
                        inv.error_count += 1
                        if inv.tipo_documento == "FEC":
                            inv.state_tributacion = "procesando"
                        else:
                            inv.state_tributacion = "procesando"
                        inv.message_post(subject=_("Error"), body=response_text)
                        _logger.error(
                            _(
                                "E-INV CR  - Invoice: %s  Status: %s Error sending XML: %s"
                                % (
                                    inv.number_electronic,
                                    response_status,
                                    response_text,
                                )
                            )
                        )
            except Exception as error:
                inv.state_tributacion = "error"
                inv.message_post(
                    subject=_("Error"),
                    body=_("Warning!.\n Error in generate_and_send_invoice: ")
                    + str(error),
                )
                continue
    
    def get_xml_attachments(self):
        """
        Método auxiliar para obtener los attachments XML desde los campos binarios
        Retorna un diccionario con los attachments encontrados
        """
        self.ensure_one()

        result = {
            'xml_documento': bool(self.xml_comprobante),
            'xml_respuesta': bool(self.xml_respuesta_tributacion),
            'has_any_xml': bool(self.xml_comprobante or self.xml_respuesta_tributacion),
        }

        return result

    def get_xml_comprobante_filename(self):
        """
        Retorna el nombre del archivo para el XML comprobante
        """
        self.ensure_one()
        if self.number_electronic:
            return f'{self.tipo_documento}_{self.number_electronic}.xml'
        return 'comprobante.xml'

    def get_xml_respuesta_filename(self):
        """
        Retorna el nombre del archivo para el XML de respuesta
        """
        self.ensure_one()
        if self.number_electronic:
            return f'AHC_{self.number_electronic}.xml'
        return 'respuesta_hacienda.xml'

    def get_zip_filename(self):
        """
        Retorna el nombre del archivo ZIP
        """
        self.ensure_one()
        if self.number_electronic:
            return f'XMLs_{self.number_electronic}.zip'
        elif self.name and self.name != '/':
            return f'XMLs_{self.name}.zip'
        return 'documentos_xml.zip'

    # -------------------------------------------------------------------------
    # BUSINESS METHODS
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company_id = vals.get("company_id") or self.env.context.get(
                "default_company_id"
            )
            partner_id = vals.get("partner_id")
            move_type = vals.get("move_type")
            partner = partner_id and self.env["res.partner"].browse(partner_id)
            if company_id:
                company = self.env["res.company"].browse(company_id)
            else:
                # Si no se especifica ninguna compañía, usa la compañía del entorno (puede ser False si no hay)
                company = self.env.company

            if (
                not vals.get("payment_methods_id")
                and company
                and company.invoice_is_electronic
                and move_type in ("out_invoice", "out_refund")
                and not self.env.context.get("install_mode")
                and not self.env.context.get("import_file")
            ):
                default_payment_method = company.payment_method_default_id
                if partner and partner.payment_methods_id:
                    vals["payment_methods_id"] = partner.payment_methods_id.id
                elif default_payment_method:
                    vals["payment_methods_id"] = default_payment_method.id
                else:
                    raise UserError(
                        _(
                            "El medio de pago está en blanco y no se ha configurado ningún Medio de Pago predeterminado "
                            f"para la compañía {company.name}. \n"
                            "Para hacerlo vaya a Ajustes Generales en la sección de Facturación Electrónica CR "
                        )
                    )

            if not vals.get("economic_activity_id"):
                if move_type in ("in_invoice", "in_refund") and partner_id:
                    vals["economic_activity_id"] = partner.activity_id.id
                elif move_type in ("out_invoice", "out_refund") and company_id:
                    vals["economic_activity_id"] = company.activity_id.id or (company.economic_activities_ids[:1].id)
            if not vals.get("tipo_documento"):
                if partner_id and partner.export:
                    vals["tipo_documento"] = "FEE"
                elif move_type == "out_refund":
                    vals["tipo_documento"] = "NC"
                elif partner_id and partner.vat:
                    if partner.country_id and partner.country_id.code != "CR":
                        vals["tipo_documento"] = "TE"
                    elif (
                        partner.identification_id
                        and partner.identification_id.code == "05"
                    ):
                        vals["tipo_documento"] = "TE"
                    else:
                        vals["tipo_documento"] = "FE"
                else:
                    vals["tipo_documento"] = "TE"
        return super().create(vals_list)

    def action_post(self):
        if not self.env.context.get("otro_texto_bypass_validation"):
            for inv in self:
                if (
                    inv.move_type in ("out_invoice", "out_refund")
                    and inv.partner_id
                    and inv.partner_id.requires_otro_texto
                ):
                    empty_fields_rules = []
                    for rule in inv.partner_id.otro_texto_rule_ids:
                        if rule.source_type == "field" and rule.value_field_id:
                            field_name = rule.value_field_id.name
                            if hasattr(inv, field_name) and not inv[field_name]:
                                empty_fields_rules.append(
                                    _(
                                        "<li>Regla para nodo '%s' (código '%s'): El campo de factura <strong>'%s'</strong> está vacío.</li>"
                                    )
                                    % (
                                        dict(rule._fields["xml_node_type"].selection).get(
                                            rule.xml_node_type
                                        ),
                                        rule.codigo or _("N/A"),
                                        rule.value_field_id.field_description,
                                    )
                                )

                    if empty_fields_rules:
                        message = _("¡Atención! Se han encontrado reglas en la pestaña 'FE: Otros' del cliente que dependen de campos de la factura que están vacíos. Esto podría generar un XML incompleto o incorrecto.")
                        message += "<ul>" + "".join(empty_fields_rules) + "</ul><br/>"
                        message += _("<strong>¿Desea validar la factura de todas formas?</strong>")

                        wizard = self.env["account.move.otro.texto.confirm"].create({
                            "move_id": inv.id,
                            "warning_message": message,
                        })

                        return {
                            "name": _("Confirmación de Campos Vacíos"),
                            "type": "ir.actions.act_window",
                            "view_mode": "form",
                            "res_model": "account.move.otro.texto.confirm",
                            "res_id": wizard.id,
                            "target": "new",
                        }

        for inv in self:
            # -------------------------------------------------------------------------
            # BLOCK: Invoice with previously rejected FE cannot generate new FE
            # -------------------------------------------------------------------------
            if inv.einvoice_had_rejection:
                raise UserError(
                    _(
                        "Esta factura tuvo un comprobante electrónico que fue rechazado por Hacienda.\n\n"
                        "Clave electrónica: %s\n"
                        "Estado: %s\n\n"
                        "No se puede validar esta factura ni generar un nuevo comprobante electrónico.\n"
                        "Debe cancelar esta factura y crear una nueva para enviar a Hacienda."
                    )
                    % (inv.number_electronic or "N/A", inv.state_tributacion or "N/A")
                )

            # Revisamos si el ambiente para Hacienda está habilitado
            if inv.company_id.frm_ws_ambiente == "disabled":
                super(AccountInvoiceElectronic, inv).action_post()
                inv.tipo_documento = "disabled"
                continue
            if inv.tipo_documento == "disabled":
                super(AccountInvoiceElectronic, inv).action_post()
                continue

            # -------------------------------------------------------------------------
            # FE VALIDATION (Client + CABYS) using validation service
            # -------------------------------------------------------------------------
            # Validate customer data and CABYS codes before generating FE
            # This prevents invalid XML generation and potential rejection by Hacienda
            validation_service = inv.env["fe.validation.service"]

            # Partner validation for FE, FEE, NC, ND
            if inv.move_type in (
                "out_invoice",
                "out_refund",
            ) and inv.tipo_documento in ("FE", "FEE", "NC", "ND"):
                # Pass reference_document_id for NC documents (to check if referencing TE)
                reference_doc = (
                    inv.reference_document_id
                    if hasattr(inv, "reference_document_id")
                    else None
                )
                is_valid, missing_fields = validation_service.validate_partner_for_fe(
                    inv.partner_id, inv.tipo_documento, reference_doc
                )
                if not is_valid:
                    validation_service.raise_partner_validation_error(
                        inv.partner_id, inv.tipo_documento, missing_fields
                    )

            # CABYS validation for all document types (except disabled)
            if inv.move_type in (
                "out_invoice",
                "out_refund",
            ) and inv.tipo_documento not in ("disabled",):
                product_lines = inv.invoice_line_ids.filtered(
                    lambda x: x.display_type == "product"
                )
                cabys_valid, cabys_errors = validation_service.validate_cabys_for_lines(
                    product_lines, inv.partner_id
                )
                if not cabys_valid:
                    validation_service.raise_cabys_validation_error(
                        inv.tipo_documento, cabys_errors
                    )

            if (
                inv.partner_id.has_exoneration
                and inv.partner_id.date_expiration
                and (inv.partner_id.date_expiration < datetime.date.today())
            ):
                raise UserError(_("The exoneration of this client has expired"))

            currency = inv.currency_id
            sequence = False
            if (inv.invoice_id) and not (
                inv.reference_code_id and inv.reference_document_id
            ):
                raise UserError(_("Incomplete reference data for credit note"))
            elif (inv.not_loaded_invoice or inv.not_loaded_invoice_date) and not (
                inv.not_loaded_invoice
                and inv.not_loaded_invoice_date
                and inv.reference_code_id
                and inv.reference_document_id
            ):
                raise UserError(
                    _("Incomplete reference data for credit note not uploaded")
                )

            if (
                inv.move_type == "in_invoice"
                and inv.partner_id.country_id
                and inv.partner_id.country_id.code == "CR"
                and inv.partner_id.identification_id
                and inv.partner_id.vat
                and inv.economic_activity_id is False
            ):
                raise UserError(
                    _(
                        "FEC invoices require that the supplier has defined the economic activity"
                    )
                )
            # tipo de identificación
            if not inv.company_id.identification_id:
                raise UserError(
                    _("Select the type of issuer identification in the company profile")
                )

            if inv.partner_id and inv.partner_id.vat:
                identificacion = re.sub("[^0-9]", "", inv.partner_id.vat)
                id_code = (
                    inv.partner_id.identification_id
                    and inv.partner_id.identification_id.code
                )
                if not id_code:
                    if len(identificacion) == 9:
                        id_code = "01"
                    elif len(identificacion) == 10:
                        id_code = "02"
                    elif len(identificacion) in (11, 12):
                        id_code = "03"
                    else:
                        id_code = "05"

                if id_code == "01" and len(identificacion) != 9:
                    raise UserError(_("The recipient's Physical ID must have 9 digits"))
                elif id_code == "02" and len(identificacion) != 10:
                    raise UserError(
                        _("The Legal ID of the recipient must have 10 digits")
                    )
                elif id_code == "03" and len(identificacion) not in (11, 12):
                    raise UserError(
                        _(
                            "The recipient's DIMEX identification must have 11 or 12 digits"
                        )
                    )
                elif id_code == "04" and len(identificacion) != 10:
                    raise UserError(
                        _("The NITE identification of the receiver must have 10 digits")
                    )

            if (
                inv.invoice_payment_term_id
                and not inv.invoice_payment_term_id.sale_conditions_id
            ):
                raise UserError(
                    _(
                        "The electronic invoice could not be created: \n"
                        "You must set up payment terms for %s"
                    )
                    % (inv.invoice_payment_term_id.name)
                )

            # Validate if invoice currency is the same as the company currency
            if currency.name != inv.company_id.currency_id.name and (
                not currency.rate_ids or not (len(currency.rate_ids) > 0)
            ):
                raise UserError(
                    _(
                        f"There is no registered exchange rate for the currency {currency.name}"
                    )
                )

            # Digital Invoice or ticket
            if inv.move_type in ("out_invoice", "out_refund") and inv.number_electronic:
                pass
            else:
                (tipo_documento, sequence) = inv.get_invoice_sequence()
                if tipo_documento and sequence:
                    inv.tipo_documento = tipo_documento
                else:
                    super(AccountInvoiceElectronic, inv).action_post()
                    continue

            # Calcular si aplica IVA Devuelto
            # Validar si el método de pago es tarjeta
            # Validar si la categoría de producto tiene marcado "Aplica Devolución IVA"
            # Validar si el IVA es la tarifa reducida del 4%
            if inv.payment_methods_id.sequence == "02":
                prod_iva_returned = self.env["product.product"].search(
                    [("name", "=", "IVA Devuelto")], limit=1
                )
                iva_returned = 0
                for inv_line in inv.invoice_line_ids:
                    if inv_line.product_id:
                        # Remove any existing IVA Devuelto lines
                        if inv_line.product_id.id == prod_iva_returned.id:
                            inv_line.unlink()
                        elif (
                            inv_line.product_id.categ_id.applies_iva_return
                            and inv_line.tax_ids.amount == 4
                        ):
                            line_tax_amount = (
                                inv_line.price_unit * inv_line.quantity
                            ) * (inv_line.tax_ids.amount / 100.0)
                            iva_returned += line_tax_amount
                if iva_returned:
                    self.amount_iva_returned = iva_returned
                    self.env["account.move.line"].create(
                        {
                            "name": "IVA Devuelto",
                            "move_id": inv.id,
                            "product_id": prod_iva_returned.id,
                            "price_unit": -iva_returned,
                            "quantity": 1,
                            "tax_ids": [(6, 0, [])],
                        }
                    )
                    # Invalidar caché para que inv.invoice_line_ids incluya la nueva línea
                    inv.invalidate_recordset(["invoice_line_ids"])

                    # =========================================================
                    # AJUSTE DE IMPUESTOS PARA EXONERACIÓN
                    # =========================================================
                    if inv.partner_id.has_exoneration:
                        # --- PASO 1: Obtener la lista de CABYS autorizados del cliente ---
                        allowed_codes = [code.name for code in inv.partner_id.allowed_cabys_ids]

                        for inv_line in inv.invoice_line_ids:
                            # --- PASO 2: Obtener el CABYS de este producto específico ---
                            cabys_code = inv_line.product_id.cabys_code or (inv_line.product_id.categ_id and inv_line.product_id.categ_id.cabys_code)
                            
                            # --- PASO 3: EL "IF" CLAVE ---
                            # Si el cliente tiene una lista restrictiva y este producto NO está en ella, 
                            # saltamos esta línea (mantenemos el IVA normal)
                            if allowed_codes and cabys_code and cabys_code not in allowed_codes:
                                _logger.info("CABYS %s no autorizado para exoneración en línea %s, se mantiene IVA normal", cabys_code, inv_line.name)
                                continue 


            super(AccountInvoiceElectronic, inv).action_post()
            if not inv.number_electronic:
                # if journal doesn't have sucursal use default from company
                sucursal_id = inv.journal_id.sucursal or self.company_id.sucursal_MR

                # if journal doesn't have terminal use default from company
                terminal_id = inv.journal_id.terminal or self.company_id.terminal_MR

                response_json = api_facturae.get_clave_hacienda(
                    inv, inv.tipo_documento, sequence, sucursal_id, terminal_id
                )

                inv.number_electronic = response_json.get("clave")
                inv.sequence = response_json.get("consecutivo")

            inv.name = inv.sequence
            inv.state_tributacion = False
            self._send_invoices_to_hacienda()

    def _post(self, soft=True):
        """
        Crear línea de exoneración SOLO para productos con CABYS autorizado.
        
        IMPORTANTE: 
        - Solo se exonera el IVA de productos cuyo CABYS esté en allowed_cabys_ids
        - Los productos sin CABYS autorizado se quedan con IVA normal
        """
        res = super()._post(soft)
        
        for move in self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund')):
            partner = move.partner_id
            
            # Validaciones básicas
            if not partner or not partner.has_exoneration:
                continue
            if partner.date_expiration and partner.date_expiration < datetime.date.today():
                continue
            if partner.percentage_exoneration <= 0:
                continue
            
            exoneration_points = partner.percentage_exoneration
            
            # Obtener códigos CABYS autorizados
            allowed_codes = []
            if partner.allowed_cabys_ids:
                allowed_codes = [code.name for code in partner.allowed_cabys_ids]
            
            _logger.info("=" * 70)
            _logger.info("EXONERACIÓN v18 - Factura: %s", move.name)
            _logger.info("Partner: %s, Puntos: %s", partner.name, exoneration_points)
            _logger.info("CABYS autorizados: %s", allowed_codes)
            
            # ═══════════════════════════════════════════════════════════════════════
            # PASO 1: Calcular exoneración POR LÍNEA DE PRODUCTO
            # ═══════════════════════════════════════════════════════════════════════
            total_exoneration = 0.0
            total_iva_original = 0.0
            iva_account_id = None
            
            # Recorrer líneas de IVA del asiento contable
            for line in move.line_ids:
                # Buscar líneas de IVA (crédito en factura, débito en NC)
                is_iva_line = False
                if line.tax_line_id and line.tax_line_id.tax_code in ['01', '04']:
                    if move.move_type == 'out_invoice' and line.credit > 0:
                        is_iva_line = True
                        iva_amount = line.credit
                    elif move.move_type == 'out_refund' and line.debit > 0:
                        is_iva_line = True
                        iva_amount = line.debit
                
                if not is_iva_line:
                    continue
                
                total_iva_original += iva_amount
                
                if iva_account_id is None:
                    iva_account_id = line.account_id
                
                # ════════════════════════════════════════════════════════════════════
                # Verificar cuánto de este IVA corresponde a productos autorizados
                # ════════════════════════════════════════════════════════════════════
                tax = line.tax_line_id
                tax_rate = tax.amount
                
                # Buscar las líneas de producto que generaron este IVA
                # y verificar si tienen CABYS autorizado
                exoneration_for_this_tax = 0.0
                
                for inv_line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                    # Verificar si esta línea tiene el impuesto actual
                    has_this_tax = False
                    for t in inv_line.tax_ids:
                        if t.id == tax.id:
                            has_this_tax = True
                            break
                    
                    if not has_this_tax:
                        continue
                    
                    # Obtener CABYS de la línea
                    cabys_code = None
                    if inv_line.product_id:
                        if inv_line.product_id.cabys_code:
                            cabys_code = inv_line.product_id.cabys_code
                        elif inv_line.product_id.categ_id and inv_line.product_id.categ_id.cabys_code:
                            cabys_code = inv_line.product_id.categ_id.cabys_code
                    
                    # Verificar si CABYS está autorizado
                    cabys_authorized = True  # Por defecto autorizado (si no hay restricción)
                    if allowed_codes and cabys_code:
                        cabys_authorized = cabys_code in allowed_codes
                    
                    if not cabys_authorized:
                        _logger.info(
                            "Producto %s: CABYS %s NO autorizado, IVA normal",
                            inv_line.name[:30], cabys_code
                        )
                        continue
                    
                    # Calcular exoneración para esta línea
                    subtotal = inv_line.price_subtotal
                    effective_points = min(exoneration_points, tax_rate)
                    line_exoneration = round(subtotal * effective_points / 100, 2)
                    
                    exoneration_for_this_tax += line_exoneration
                    
                    _logger.info(
                        "Producto %s: CABYS %s autorizado, exoneración=%s",
                        inv_line.name[:30], cabys_code or "N/A", line_exoneration
                    )
                
                # Limitar exoneración al monto del IVA de este impuesto
                exoneration_for_this_tax = min(exoneration_for_this_tax, iva_amount)
                total_exoneration += exoneration_for_this_tax
                
                _logger.info(
                    "IVA %s: monto=%s, exoneración calculada=%s",
                    tax.name, iva_amount, exoneration_for_this_tax
                )
            
            total_exoneration = round(total_exoneration, 2)
            
            _logger.info("TOTAL IVA original: %s", total_iva_original)
            _logger.info("TOTAL exoneración: %s", total_exoneration)
            
            if total_exoneration <= 0:
                _logger.info("Sin exoneración que aplicar")
                continue
            
            if iva_account_id is None:
                _logger.warning("No se encontró cuenta de IVA")
                continue
            
            # ═══════════════════════════════════════════════════════════════════════
            # PASO 2: Crear UNA línea de exoneración
            # ═══════════════════════════════════════════════════════════════════════
            MoveLine = self.env['account.move.line']
            
            line_vals = {
                'move_id': move.id,
                'account_id': iva_account_id.id,
                'name': 'Exoneración IVA',
                'partner_id': partner.id,
                'currency_id': move.currency_id.id,
            }
            
            if move.move_type == 'out_invoice':
                line_vals['debit'] = total_exoneration
                line_vals['credit'] = 0.0
            else:
                line_vals['debit'] = 0.0
                line_vals['credit'] = total_exoneration
            
            new_line = MoveLine.with_context(check_move_validity=False).create(line_vals)
            
            _logger.info(
                "Línea exoneración creada: cuenta=%s, débito=%s, crédito=%s",
                new_line.account_id.code, new_line.debit, new_line.credit
            )
            
            # ═══════════════════════════════════════════════════════════════════════
            # PASO 3: Reducir línea del cliente
            # ═══════════════════════════════════════════════════════════════════════
            move.invalidate_recordset(['line_ids'])
            partner_line = move.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            )
            
            if partner_line:
                if move.move_type == 'out_invoice':
                    old = partner_line.debit
                    partner_line.with_context(check_move_validity=False).debit = old - total_exoneration
                    _logger.info("Cliente débito: %s → %s", old, partner_line.debit)
                else:
                    old = partner_line.credit
                    partner_line.with_context(check_move_validity=False).credit = old - total_exoneration
                    _logger.info("Cliente crédito: %s → %s", old, partner_line.credit)
            
            # ═══════════════════════════════════════════════════════════════════════
            # PASO 4: Verificar balance
            # ═══════════════════════════════════════════════════════════════════════
            move.flush_recordset(['line_ids'])
            move.invalidate_recordset(['line_ids'])
            
            total_debit = sum(move.line_ids.mapped('debit'))
            total_credit = sum(move.line_ids.mapped('credit'))
            diff = round(total_credit - total_debit, 2)
            
            _logger.info("-" * 70)
            _logger.info("BALANCE: Débito=%s, Crédito=%s, Diff=%s", total_debit, total_credit, diff)
            
            if abs(diff) > 0.01:
                _logger.warning("Corrigiendo desbalance: %s", diff)
                partner_line = move.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'
                )
                if partner_line:
                    if move.move_type == 'out_invoice':
                        partner_line.debit = partner_line.debit + diff
                    else:
                        partner_line.credit = partner_line.credit + diff
                    move.flush_recordset(['line_ids'])
            
            # Guardar referencia
            move.write({
                'amount_exoneration': total_exoneration,
                'amount_tax_before_exoneration': total_iva_original,
            })
            
            _logger.info("=" * 70)
        
        return res

    def _reverse_move_vals(self, default_values, cancel=True):
        move_vals = super()._reverse_move_vals(default_values, cancel)
        # type_override = move_vals.get('type_override')
        # if type_override:
        #     move_vals['move_type'] = type_override
        #     move_vals.pop('type_override')
        return move_vals

    def create_partner_from_xml(self):

        if not self.partner_id and self.xml_supplier_approval:
            info = {}

            invoice_xml = etree.fromstring(base64.b64decode(self.xml_supplier_approval))
            namespaces = invoice_xml.nsmap
            inv_xmlns = namespaces.pop(None)
            namespaces["inv"] = inv_xmlns

            info["vat"] = invoice_xml.xpath(
                "inv:Emisor/inv:Identificacion/inv:Numero", namespaces=namespaces
            )[0].text

            partner = self.env["res.partner"].search(
                [("vat", "=", info["vat"])], limit=1
            )
            if len(partner) > 0:
                self.partner_id = partner.id
            else:
                info["name"] = invoice_xml.xpath(
                    "inv:Emisor/inv:Nombre", namespaces=namespaces
                )[0].text
                info["phone"] = (
                    invoice_xml.xpath(
                        "inv:Emisor/inv:Telefono/inv:NumTelefono", namespaces=namespaces
                    )[0].text
                    or False
                )
                info["email"] = (
                    invoice_xml.xpath(
                        "inv:Emisor/inv:CorreoElectronico", namespaces=namespaces
                    )[0].text
                    or False
                )
                info["lang"] = "es_CR"

                # Se agrega manualmente la información ya que no se puede obtener del XML
                info["property_payment_term_id"] = 1
                info["payment_methods_id"] = 1
                info["property_product_pricelist"] = 1
                info["property_supplier_payment_term_id"] = 1

                # País
                info["country_id"] = (
                    self.env["res.country"].search([("code", "=", "CR")], limit=1).id
                )

                # Provincia
                provincia = invoice_xml.xpath(
                    "inv:Emisor/inv:Ubicacion/inv:Provincia", namespaces=namespaces
                )[0].text
                state_id = (
                    self.env["res.country.state"]
                    .search([("code", "=", provincia)], limit=1)
                    .id
                )
                info["state_id"] = state_id

                # Cantón
                canton = invoice_xml.xpath(
                    "inv:Emisor/inv:Ubicacion/inv:Canton", namespaces=namespaces
                )[0].text
                county_id = (
                    self.env["res.country.county"]
                    .search(
                        [("code", "=", canton), ("state_id", "=", state_id)], limit=1
                    )
                    .id
                )
                info["county_id"] = county_id

                # Distrito
                distrito = invoice_xml.xpath(
                    "inv:Emisor/inv:Ubicacion/inv:Distrito", namespaces=namespaces
                )[0].text
                district_id = (
                    self.env["res.country.district"]
                    .search(
                        [("code", "=", distrito), ("county_id", "=", county_id)],
                        limit=1,
                    )
                    .id
                )
                info["district_id"] = district_id

                actividad_economica = invoice_xml.xpath(
                    "inv:CodigoActividad", namespaces=namespaces
                )[0].text
                info["activity_id"] = (
                    self.env["economic.activity"]
                    .search([("code", "=", actividad_economica)], limit=1)
                    .id
                )

                cliente = self.env["res.partner"].create(info)
                cliente.onchange_vat()
                self.partner_id = cliente.id

    # ------------------------------------------------------------
    # MAIL.THREAD
    # ------------------------------------------------------------

    def get_xml_document(self, invoice_id):
        tab_id = []
        domain = [
            ("res_model", "=", "account.move"),
            ("res_id", "=", invoice_id),
            ("res_field", "=", "xml_comprobante"),
        ]
        attachment = self.env["ir.attachment"].sudo().search(domain, limit=1)
        if attachment:
            tab_id.append(attachment.id)
            domain_resp = [
                ("res_model", "=", "account.move"),
                ("res_id", "=", invoice_id),
                ("res_field", "=", "xml_respuesta_tributacion"),
            ]
            attachment_resp = (
                self.env["ir.attachment"].sudo().search(domain_resp, limit=1)
            )

            if attachment_resp:
                tab_id.append(attachment_resp.id)

        url = f"/web/binary/download_document?tab_id={tab_id}&invoice_id={invoice_id}"
        return url

    def action_invoice_sent_mass(self):
        if self.invoice_id.move_type in ["in_invoice", "in_refund"]:
            template_name = "account.email_template_edi_invoice"
            email_template = self.env.ref(template_name, raise_if_not_found=False)
        else:
            email_template = self.env.ref(
                "account.email_template_edi_invoice", raise_if_not_found=False
            )

        lang = False
        if email_template:
            # Utilizamos el contexto de la compañía activa para asegurarnos de que la plantilla esté disponible
            lang = email_template.with_context(
                allowed_company_ids=[self.company_id.id]
            )._render_lang(self.ids)[self.id]
        if not lang:
            lang = get_lang(self.env).code

        # Verificamos si el ambiente de la compañía está desactivado
        if self.company_id.frm_ws_ambiente == "disabled":
            pass
        elif self.partner_id and self.partner_id.email:
            # Agregamos filtro de compañía en el dominio para buscar el adjunto de comprobante
            domain = [
                ("res_model", "=", "account.move"),
                ("res_id", "=", self.id),
                ("res_field", "=", "xml_comprobante"),
            ]
            attachment = self.env["ir.attachment"].sudo().search(domain, limit=1)

            if not attachment:
                _logger.warning(
                    "No se encontró el archivo XML de comprobante para la factura %s",
                    self.id,
                )
            else:
                _logger.info("XML comprobante encontrado: %s", attachment.name)

            # Agregamos filtro de compañía en el dominio para buscar el adjunto de respuesta tributaria
            domain_resp = [
                ("res_model", "=", "account.move"),
                ("res_id", "=", self.id),
                ("res_field", "=", "xml_respuesta_tributacion"),
            ]
            attachment_resp = (
                self.env["ir.attachment"].sudo().search(domain_resp, limit=1)
            )

            if not attachment_resp:
                _logger.warning(
                    "No se encontró el archivo XML de respuesta tributaria para la factura %s",
                    self.id,
                )
            else:
                _logger.info(
                    "XML respuesta tributaria encontrado: %s", attachment_resp.name
                )

            # Solo si ambos archivos existen, los adjuntamos al correo
            if attachment and attachment_resp:
                # Copiamos los adjuntos para agregarlos al correo
                attach_copy = attachment.copy()
                attach_resp_copy = attachment_resp.copy()
                email_template.attachment_ids = [
                    (6, 0, [attach_copy.id, attach_resp_copy.id])
                ]

                # Enviamos el correo con los adjuntos
                email_template.with_context(
                    type="binary", default_type="binary"
                ).send_mail(self.id, raise_exception=False, force_send=True)
                _logger.info("E-INV CR - MASS SEND - Exitoso: %s", self.sequence)

                # Limpiamos los adjuntos para evitar problemas en futuras llamadas
                email_template.attachment_ids = [(5, 0, 0)]

    def action_invoice_sent(self):
        self.ensure_one()

        if self.invoice_id.move_type in ["in_invoice", "in_refund"]:
            template_name = "cr_electronic_invoice.email_template_invoice_vendor"
            email_template = self.env.ref(template_name, raise_if_not_found=False)
        else:
            email_template = self.env.ref(
                "account.email_template_edi_invoice", raise_if_not_found=False
            )

        lang = False
        if email_template:
            lang = email_template._render_lang(self.ids)[self.id]
        if not lang:
            lang = get_lang(self.env).code

        if self.env.user.company_id.frm_ws_ambiente == "disabled":
            pass
        elif self.partner_id and self.partner_id.email:
            # Limpiar attachments previos del template
            email_template.attachment_ids = [(5, 0, 0)]

            # Lista para almacenar todos los attachments
            attachment_ids = []

            # 1. Generar PDF de la factura
            pdf_content, pdf_format = (
                self.env["ir.actions.report"]
                .sudo()
                ._render("account.account_invoices", [self.id])
            )
            pdf_attachment = (
                self.env["ir.attachment"]
                .sudo()
                .create(
                    {
                        "name": (
                            f"{self.tipo_documento}_{self.number_electronic}.pdf"
                            if self.tipo_documento
                            else f"{self.name}.pdf"
                        ),
                        "type": "binary",
                        "datas": base64.b64encode(pdf_content),
                        "res_model": self._name,
                        "res_id": self.id,
                        "mimetype": "application/pdf",
                    }
                )
            )
            attachment_ids.append(pdf_attachment.id)

            # 2. Buscar XML comprobante
            domain = [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("res_field", "=", "xml_comprobante"),
            ]
            attachment_xml = self.env["ir.attachment"].sudo().search(domain, limit=1)
            if attachment_xml:
                attach_xml_copy = attachment_xml.copy()
                attachment_ids.append(attach_xml_copy.id)

                # 3. Buscar XML respuesta tributación
                domain_resp = [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("res_field", "=", "xml_respuesta_tributacion"),
                ]
                attachment_resp = (
                    self.env["ir.attachment"].sudo().search(domain_resp, limit=1)
                )

                if attachment_resp:
                    attach_resp_copy = attachment_resp.copy()
                    attachment_ids.append(attach_resp_copy.id)
                else:
                    raise UserError(
                        _("Response XML from Hacienda has not been received")
                    )
            else:
                raise UserError(
                    _("Invoice XML has not been generated for id:" + str(self.id))
                )

            # Asignar todos los attachments al template
            email_template.attachment_ids = [(6, 0, attachment_ids)]

        else:
            raise UserError(_("Partner is not assigned to this invoice"))

        # Contexto para mail.compose.message
        ctx = {
            "default_model": "account.move",
            "default_res_ids": [self.id],
            "default_template_id": email_template.id if email_template else False,
            "default_use_template": bool(email_template),
            "default_composition_mode": "comment",
            "mark_invoice_as_sent": True,
            "force_email": True,
            # Importante: incluir el attachment_ids en el contexto también
            "default_attachment_ids": (
                attachment_ids if "attachment_ids" in locals() else []
            ),
        }

        return {
            "name": "Send Invoice",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mail.compose.message",
            "target": "new",
            "context": ctx,
        }
