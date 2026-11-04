# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import io
import zipfile
from odoo import http
from odoo.addons.account.controllers.portal import PortalAccount
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, MissingError


class PortalAccountCustom(PortalAccount):
    """
    Controlador personalizado para el portal de facturas
    Agrega funcionalidad para descargar documentos XML de facturación electrónica
    """

    def _invoice_get_page_view_values(self, invoice, access_token, **kwargs):
        """
        Sobrescribe el método para agregar los attachments XML
        """
        # Llamar al método padre para obtener valores base
        values = super()._invoice_get_page_view_values(invoice, access_token, **kwargs)

        # Agregar información de los XMLs disponibles
        xml_attachments = invoice.get_xml_attachments()
        values.update(xml_attachments)

        return values

    @http.route(['/my/invoices/<int:invoice_id>/download_xml'], type='http', auth="public", website=True)
    def portal_invoice_download_xml(self, invoice_id, xml_type='documento', access_token=None, **kw):
        """
        Descarga el XML de la factura desde los campos binarios

        Args:
            invoice_id: ID de la factura
            xml_type: 'documento' o 'respuesta'
            access_token: Token de acceso para validación
        """
        try:
            # Verificar acceso a la factura
            invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Determinar qué XML descargar
        xml_content = None
        filename = None

        if xml_type == 'respuesta':
            if invoice_sudo.xml_respuesta_tributacion:
                xml_content = base64.b64decode(invoice_sudo.xml_respuesta_tributacion)
                filename = invoice_sudo.get_xml_respuesta_filename()
        else:  # documento
            if invoice_sudo.xml_comprobante:
                xml_content = base64.b64decode(invoice_sudo.xml_comprobante)
                filename = invoice_sudo.get_xml_comprobante_filename()

        # Si no existe el XML, redirigir a la factura
        if not xml_content or not filename:
            return request.redirect(f'/my/invoices/{invoice_id}?access_token={access_token}')

        # Preparar la respuesta HTTP para descarga
        headers = [
            ('Content-Type', 'application/xml'),
            ('Content-Disposition', content_disposition(filename)),
            ('Content-Length', len(xml_content))
        ]

        return request.make_response(xml_content, headers=headers)

    @http.route(['/my/invoices/<int:invoice_id>/download_xmls_zip'], type='http', auth="public", website=True)
    def portal_invoice_download_xmls_zip(self, invoice_id, access_token=None, **kw):
        """
        Descarga un archivo ZIP conteniendo los XMLs de la factura

        Args:
            invoice_id: ID de la factura
            access_token: Token de acceso para validación
        """
        try:
            # Verificar acceso a la factura
            invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Verificar que exista al menos un XML
        if not invoice_sudo.xml_comprobante and not invoice_sudo.xml_respuesta_tributacion:
            return request.redirect(f'/my/invoices/{invoice_id}?access_token={access_token}')

        # Crear el archivo ZIP en memoria
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Agregar XML del comprobante si existe
            if invoice_sudo.xml_comprobante:
                xml_content = base64.b64decode(invoice_sudo.xml_comprobante)
                filename = invoice_sudo.get_xml_comprobante_filename()
                zip_file.writestr(filename, xml_content)

            # Agregar XML de respuesta de Hacienda si existe
            if invoice_sudo.xml_respuesta_tributacion:
                xml_content = base64.b64decode(invoice_sudo.xml_respuesta_tributacion)
                filename = invoice_sudo.get_xml_respuesta_filename()
                zip_file.writestr(filename, xml_content)

        # Obtener el contenido del ZIP
        zip_content = zip_buffer.getvalue()
        zip_buffer.close()

        # Preparar la respuesta HTTP para descarga
        zip_filename = invoice_sudo.get_zip_filename()
        headers = [
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', content_disposition(zip_filename)),
            ('Content-Length', len(zip_content))
        ]

        return request.make_response(zip_content, headers=headers)