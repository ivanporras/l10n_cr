# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


import re
import json
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import phonenumbers
import logging
from datetime import datetime, timedelta, date
from . import api_facturae

_logger = logging.getLogger(__name__)


class PartnerElectronic(models.Model):
    _description = 'Partner Electronic'
    _inherit = "res.partner"

    # ==============================================================================================
    #                                          PARTNER
    # ==============================================================================================

    # === Partner fields === #

    commercial_name = fields.Char(
        string='Nombre Comercial'
    )
    identification_id = fields.Many2one(
        comodel_name="identification.type",
        string='Tipo de Identificación'
    )
    payment_methods_id = fields.Many2one(
        comodel_name="payment.methods",
        string="Método de Pago"
    )
    export = fields.Boolean(
        string="Es Exportación",
        default=False
    )
    inscribed = fields.Boolean(
        string="Inscrito",
        readonly=True,
        store=True
    )

    # === Economic Activity fields === #

    activity_id = fields.Many2one(
        comodel_name="economic.activity",
        string="Actividad Económica Principal",
        context={'active_test': False},
        check_company=False,
    )
    economic_activities_ids = fields.Many2many(
        comodel_name='economic.activity',
        string='Actividades Económicas',
        context={'active_test': False},
        check_company=False,
    )
    # Indicador principal de exoneración
    has_exoneration = fields.Boolean(
        string="Tiene Exoneración",
        default=False,
        required=False,
        tracking=True
    )

    # --- Tipo de Documento de Exoneración (Nota 10.1) ---
    type_exoneration = fields.Many2one(
        comodel_name="aut.ex",
        string="Tipo de Documento",
        help="Tipo de documento de exoneración o autorización según Nota 10.1"
    )
    
    # Campo para descripción cuando tipo = 99 (Otros)
    type_exoneration_other = fields.Char(
        string="Tipo de Documento OTRO",
        size=100,
        help="Descripción del tipo de documento cuando se selecciona 'Otros' (código 99). "
             "Debe contener mínimo 5 caracteres y un máximo de 100."
    )

    # --- Número de Documento ---
    exoneration_number = fields.Char(
        string="Número de Documento",
        size=40,
        help="Número de documento de exoneración o autorización. "
             "Debe indicarse tal como aparece en el documento otorgado por la institución, "
             "incluyendo guiones. En caso de códigos 02 o 03 y 08, debe indicar el número de la ley."
    )

    # --- Artículo e Inciso (para códigos 02, 03, 06, 07, 08) ---
    exoneration_article = fields.Integer(
        string="Número de Artículo",
        compute='_compute_exoneration_legal_defaults',
        store=True,
        readonly=False,
        help="Número del artículo de la ley que establece la exoneración o autorización. "
             "Obligatorio para códigos 02, 03, 06, 07 y 08 de la Nota 10.1."
    )
    
    exoneration_inciso = fields.Integer(
        string="Número de Inciso",
        compute='_compute_exoneration_legal_defaults',
        store=True,
        readonly=False,
        help="Número del inciso del artículo que establece la exoneración. "
             "Obligatorio cuando el artículo hace referencia a un inciso."
    )

    # --- Institución Emisora (Nota 23) ---
    institution_id = fields.Many2one(
        comodel_name="institution.exoneration",
        string="Institución Emisora",
        help="Código de la institución que emitió la exoneración según Nota 23"
    )
    
    # Campo para nombre de institución cuando código = 99 (Otros)
    institution_name_other = fields.Char(
        string="Nombre Institución OTRO",
        size=160,
        help="Nombre de la institución cuando se selecciona 'Otros' (código 99). "
             "Debe contener mínimo 5 caracteres y un máximo de 160."
    )
    
    # Campo legacy - mantener por compatibilidad con datos existentes
    institution_name = fields.Char(
        string="Institución Emisora (Legacy)",
        help="Campo legacy. Se recomienda usar institution_id para nuevos registros."
    )

    # --- Tarifa Exonerada ---
    percentage_exoneration = fields.Float(
        string="Tarifa Exonerada (%)",
        digits=(4, 2),
        required=False,
        help="Porcentaje o tarifa de exoneración (formato decimal 4,2). "
             "Ejemplos: 13.00, 1.00, 0.50. "
             "Se obtiene de la multiplicación: (Suma montos exonerados / Suma montos impuesto)"
    )
    
    # --- Autorizacion de la Exoneracion ---
    authorization_exoneration = fields.Char(
        string="Autrización",
        help="Número de autorización de la exoneración"
    )

    # --- Fechas ---
    date_issue = fields.Date(
        string="Fecha de Emisión",
        help="Fecha de emisión del documento de exoneración"
    )
    
    date_expiration = fields.Date(
        string="Fecha de Vencimiento",
        help="Fecha de vencimiento de la exoneración"
    )
    
    date_notification = fields.Date(
        string="Última Notificación",
        help="Fecha de la última notificación enviada sobre vencimiento de exoneración"
    )

    # --- Códigos CABYS Autorizados ---
    allowed_cabys_ids = fields.One2many(
        comodel_name='res.partner.cabys.line',
        inverse_name='parent_id',
        string='Códigos CABYS Autorizados',
        help="Códigos CABYS autorizados para esta exoneración. "
             "En caso de aplicarse exoneración, el código CABYS debe estar en esta lista."
    )

    # ==============================================================================================
    #                          CAMPOS PARA REGLAS DE OTROTEXTO
    # ==============================================================================================

    requires_otro_texto = fields.Boolean(
        string="¿Requiere OtroTexto Personalizado?",
        help="Marque esta opción si este cliente requiere nodos <OtroTexto> personalizados en el XML de la factura electrónica.",
        default=False,
    )

    otro_texto_rule_ids = fields.One2many(
        "res.partner.otro.texto.rule",
        "partner_id",
        string="Reglas de OtroTexto",
    )

    # ==============================================================================================
    #                          COMPUTED FIELDS FOR VALIDATIONS
    # ==============================================================================================

    requires_article = fields.Boolean(
        string='Requiere Artículo',
        compute='_compute_requires_article',
        store=True,
        help="Indica si el tipo de documento requiere número de artículo"
    )
    
    requires_institution_other = fields.Boolean(
        string='Requiere Nombre Institución OTRO',
        compute='_compute_requires_institution_other',
        store=True,
        help="Indica si se requiere especificar el nombre de la institución"
    )
    
    requires_type_other = fields.Boolean(
        string='Requiere Tipo Documento OTRO',
        compute='_compute_requires_type_other',
        store=True,
        help="Indica si se requiere especificar el tipo de documento"
    )
    
    exoneration_is_valid = fields.Boolean(
        string='Exoneración Válida',
        compute='_compute_exoneration_is_valid',
        store=False,
        help="Indica si la exoneración está vigente y completa"
    )

    # ==============================================================================================
    #                          ONCHANGE METHODS
    # ==============================================================================================

    @api.onchange('phone')
    def _onchange_phone(self):
        if self.phone:
            try:
                phone = phonenumbers.parse(self.phone, self.country_id and self.country_id.code or 'CR')
                valid = phonenumbers.is_valid_number(phone)
                if not valid:
                    alert = {
                        'title': 'Atención',
                        'message': _('Número de teléfono inválido')
                    }
                    return {'value': {'phone': ''}, 'warning': alert}
            except Exception:
                pass

    @api.onchange('mobile')
    def _onchange_mobile(self):
        if self.mobile:
            try:
                mobile = phonenumbers.parse(self.mobile, self.country_id and self.country_id.code or 'CR')
                valid = phonenumbers.is_valid_number(mobile)
                if not valid:
                    alert = {
                        'title': 'Atención',
                        'message': _('Número de teléfono inválido')
                    }
                    return {'value': {'mobile': ''}, 'warning': alert}
            except Exception:
                pass

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            if not re.match(r'^(\s?[^\s,]+@[^\s,]+\.[^\s,]+\s?,)*(\s?[^\s,]+@[^\s,]+\.[^\s,]+)$', self.email.lower()):
                vals = {'email': False}
                alerta = {
                    'title': 'Atención',
                    'message': 'El correo electrónico no cumple con una estructura válida. ' + str(self.email)
                }
                return {'value': vals, 'warning': alerta}

    @api.onchange('vat')
    def _onchange_vat(self):
        if self.identification_id and self.vat:
            if self.identification_id.code == '05':
                if len(self.vat) == 0 or len(self.vat) > 20:
                    raise UserError(_('La identificación debe tener menos de 20 caracteres.'))
            else:
                # Remove letters, dashes, dots or any other special character.
                self.vat = re.sub(r"[^0-9]+", "", self.vat)
                if self.identification_id.code == '01':
                    if self.vat.isdigit() and len(self.vat) != 9:
                        raise UserError(_('La identificación tipo Cédula física debe ' +
                                        'contener 9 dígitos, sin cero al inicio y sin guiones.'))
                elif self.identification_id.code == '02':
                    if self.vat.isdigit() and len(self.vat) != 10:
                        raise UserError(_('La identificación tipo Cédula jurídica debe contener 10 ' +
                                          'dígitos, sin cero al inicio y sin guiones.'))
                elif self.identification_id.code == '03' and self.vat.isdigit():
                    if self.vat.isdigit() and len(self.vat) < 11 or len(self.vat) > 12:
                        raise UserError(_('La identificación tipo DIMEX debe contener 11 o 12 ' +
                                          'dígitos, sin ceros al inicio y sin guiones.'))
                elif self.identification_id.code == '04' and self.vat.isdigit():
                    if self.vat.isdigit() and len(self.vat) != 9:
                        raise UserError(_('La identificación tipo NITE debe contener 10 dígitos, ' +
                                          'sin ceros al inicio y sin guiones.'))

    @api.onchange('exoneration_number')
    def _onchange_exoneration_number(self):
        """Cargar información de exoneración desde API externa si está configurada"""
        if self.exoneration_number:
            self.definir_informacion_exo(self.exoneration_number)

    @api.onchange('zip')
    def _onchange_zip_custom(self):
        for record in self:
            zip_code = record.zip
            if zip_code and not (record.state_id or record.county_id or record.district_id or record.neighborhood_id):
                state = zip_code[:1]
                county = zip_code[1:3]
                district = zip_code[3:5]

                state_id = self.env['res.country.state'].search([('code', '=', state)], limit=1)
                record.state_id = state_id.id

    @api.onchange('type_exoneration')
    def _onchange_type_exoneration(self):
        """Limpiar campos cuando cambia el tipo de exoneración"""
        if self.type_exoneration and self.type_exoneration.code != '99':
            self.type_exoneration_other = False

    @api.onchange('institution_id')
    def _onchange_institution_id(self):
        """Limpiar campo OTRO cuando cambia la institución"""
        if self.institution_id and self.institution_id.code != '99':
            self.institution_name_other = False

    # ==============================================================================================
    #                          COMPUTE METHODS
    # ==============================================================================================

    @api.depends('type_exoneration')
    def _compute_exoneration_legal_defaults(self):
        """
        Carga automática de valores legales estándar basados en la Nota 10.1
        según la Ley 9635 (Ley de IVA).
        """
        dgt_institution = self.env['institution.exoneration'].search([('code', '=', '01')], limit=1)
        default_date = date(2019, 7, 1)

        for record in self:
            if record.type_exoneration:
                # Fecha de emisión estándar para Ley 9635
                record.date_issue = default_date
                
                # Institución por defecto (DGT)
                if dgt_institution:
                    record.institution_id = dgt_institution.id

                code = record.type_exoneration.code
                if code == '08':  # Zona Franca
                    record.exoneration_article = 8
                    record.exoneration_inciso = 2
                elif code == '10':  # Municipalidades
                    record.exoneration_article = 8
                    record.exoneration_inciso = 4
                elif code == '09':  # Exportación de Servicios
                    record.exoneration_article = 11
                    record.exoneration_inciso = 0
                elif code == '03':  # Ley Especial
                    record.exoneration_article = 2
                    record.exoneration_inciso = 0
                else:
                    # No sobreescribir si no hay mapeo definido para otros códigos
                    pass
            else:
                record.exoneration_article = 0
                record.exoneration_inciso = 0

    @api.depends('type_exoneration')
    def _compute_requires_article(self):
        """
        Los códigos 02, 03, 06, 07 y 08 requieren número de artículo según Nota 10.1
        """
        for record in self:
            record.requires_article = (
                record.type_exoneration and
                record.type_exoneration.code in ('02', '03', '06', '07', '08')
            )

    @api.depends('institution_id')
    def _compute_requires_institution_other(self):
        """El código 99 requiere nombre de institución adicional"""
        for record in self:
            record.requires_institution_other = (
                record.institution_id and
                record.institution_id.code == '99'
            )

    @api.depends('type_exoneration')
    def _compute_requires_type_other(self):
        """El código 99 requiere descripción del tipo de documento"""
        for record in self:
            record.requires_type_other = (
                record.type_exoneration and
                record.type_exoneration.code == '99'
            )

    @api.depends('has_exoneration', 'type_exoneration', 'exoneration_number', 
                 'institution_id', 'percentage_exoneration', 'date_issue',
                 'date_expiration')
    def _compute_exoneration_is_valid(self):
        """Verifica si la exoneración está completa y vigente"""
        today = date.today()
        for record in self:
            if not record.has_exoneration:
                record.exoneration_is_valid = False
                continue

            # Verificar campos obligatorios
            is_valid = bool(
                record.type_exoneration and
                record.exoneration_number and
                record.institution_id and
                record.percentage_exoneration > 0 and
                record.date_issue
            )

            # Verificar fecha de vencimiento
            if is_valid and record.date_expiration:
                is_valid = record.date_expiration >= today

            # Verificar campos condicionales
            if is_valid and record.requires_article:
                is_valid = bool(record.exoneration_article)

            if is_valid and record.requires_type_other:
                is_valid = bool(record.type_exoneration_other and len(record.type_exoneration_other) >= 5)

            if is_valid and record.requires_institution_other:
                is_valid = bool(record.institution_name_other and len(record.institution_name_other) >= 5)

            record.exoneration_is_valid = is_valid

    # ==============================================================================================
    #                          CONSTRAINT METHODS
    # ==============================================================================================

    @api.constrains('has_exoneration', 'type_exoneration', 'type_exoneration_other')
    def _check_type_exoneration_other(self):
        """Validar campo OTRO cuando tipo = 99"""
        for record in self:
            if record.has_exoneration and record.requires_type_other:
                if not record.type_exoneration_other:
                    raise ValidationError(_(
                        'El campo "Tipo de Documento OTRO" es obligatorio cuando '
                        'selecciona "Otros" (código 99) como tipo de exoneración.'
                    ))
                if len(record.type_exoneration_other) < 5:
                    raise ValidationError(_(
                        'El campo "Tipo de Documento OTRO" debe contener al menos 5 caracteres.'
                    ))

    @api.constrains('has_exoneration', 'type_exoneration', 'exoneration_article')
    def _check_exoneration_article(self):
        """Validar artículo cuando es requerido"""
        for record in self:
            if record.has_exoneration and record.requires_article:
                if not record.exoneration_article:
                    raise ValidationError(_(
                        'El campo "Número de Artículo" es obligatorio para el tipo '
                        'de exoneración seleccionado (códigos 02, 03, 06, 07, 08).'
                    ))

    @api.constrains('has_exoneration', 'institution_id', 'institution_name_other')
    def _check_institution_name_other(self):
        """Validar nombre de institución cuando código = 99"""
        for record in self:
            if record.has_exoneration and record.requires_institution_other:
                if not record.institution_name_other:
                    raise ValidationError(_(
                        'El campo "Nombre Institución OTRO" es obligatorio cuando '
                        'selecciona "Otros" (código 99) como institución emisora.'
                    ))
                if len(record.institution_name_other) < 5:
                    raise ValidationError(_(
                        'El campo "Nombre Institución OTRO" debe contener al menos 5 caracteres.'
                    ))

    @api.constrains('has_exoneration', 'exoneration_number')
    def _check_exoneration_number(self):
        """Validar número de documento"""
        for record in self:
            if record.has_exoneration and record.exoneration_number:
                if len(record.exoneration_number) < 3:
                    raise ValidationError(_(
                        'El número de documento de exoneración debe tener al menos 3 caracteres.'
                    ))

    @api.constrains('has_exoneration', 'percentage_exoneration')
    def _check_percentage_exoneration(self):
        """Validar porcentaje de exoneración"""
        for record in self:
            if record.has_exoneration:
                if record.percentage_exoneration <= 0:
                    raise ValidationError(_(
                        'La tarifa exonerada debe ser mayor a 0.'
                    ))
                if record.percentage_exoneration > 100:
                    raise ValidationError(_(
                        'La tarifa exonerada no puede ser mayor a 100.'
                    ))

    # ==============================================================================================
    #                          TOOLING
    # ==============================================================================================

    def action_get_economic_activities(self):
        """Obtener actividades económicas desde API de Hacienda"""
        if not self.vat:
            return {
                'value': {'vat': ''},
                'warning': {
                    'title': 'Atención',
                    'message': _('La identificación de la empresa es inválida')
                }
            }

        json_response = api_facturae.get_economic_activities(self)
        _logger.debug('E-INV CR - Economic Activities: %s', json_response)

        status = str(json_response.get("status", "")).strip()
        if status != "200":
            alert = {
                'title': status,
                'message': json_response.get("text") or json_response.get("message") or "Error desconocido"
            }
            return {'value': {'vat': ''}, 'warning': alert}

        # Obtener lista de actividades
        activities = json_response.get("activities") or json_response.get("actividades") or []

        activities_to_link = self.env['economic.activity']
        primary_activity = False

        for act in activities:
            estado = act.get("estado") or act.get("status")
            if not str(estado).upper().startswith("A"):  # Solo procesar Activas
                continue

            code = str(act.get("codigo") or act.get("code") or '').strip()
            if not code:
                continue

            name = act.get("descripcion") or act.get("name") or ''
            tipo = str(act.get("tipo") or 'S').upper()  # P=Principal, S=Secundaria

            # Buscamos la actividad (en esta compañía)
            existing = self.env['economic.activity'].with_context(active_test=False).search([
                ('code', '=', code),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            if existing:
                # IMPORTANTE: Actualizar con nombre exacto de Hacienda y Activar
                existing.write({
                    'name': name,
                    'active': True
                })
            else:
                # Si no existe, crearla estrictamente con los datos de Hacienda
                existing = self.env['economic.activity'].create({
                    'code': code,
                    'name': name,
                    'active': True,
                    'company_id': self.env.company.id,
                })

            activities_to_link |= existing

            # Asignar como principal si el tipo es 'P'
            if tipo == 'P':
                primary_activity = existing

        # Sincronización estricta de actividades en el partner
        self.economic_activities_ids = [(6, 0, activities_to_link.ids)]

        if not primary_activity and activities_to_link:
            primary_activity = activities_to_link[0]

        self.activity_id = primary_activity.id if primary_activity else False

        # Actualizar datos del partner
        self.name = json_response.get("name") or self.name
        situacion = (json_response.get("situacion", "") or "").strip()
        self.inscribed = situacion.lower() in ("inscrito", "inscrito de oficio")
        return True

    def definir_informacion_exo(self, cedula):
        """
        Obtener información de exoneración desde API externa.
        
        Esta función consulta una API externa configurada en la compañía
        para obtener los datos de exoneración del cliente.
        """
        url_base = self.sudo().env.company.url_base_exo
        if not url_base:
            return

        url_base = url_base.strip()
        if url_base[-1:] == '/':
            url_base = url_base[:-1]

        end_point = url_base + 'autorizacion=' + cedula

        headers = {
            'content-type': 'application/json',
        }

        try:
            peticion = requests.get(end_point, headers=headers, timeout=10)
        except requests.exceptions.RequestException as e:
            _logger.warning('Error consultando API de exoneración: %s', str(e))
            return

        ultimo_mensaje = 'Fecha/Hora: ' + str(datetime.now()) + ', Codigo: ' + str(
            peticion.status_code) + ', Mensaje: ' + str(peticion._content.decode())

        if peticion.status_code in (200, 202) and len(peticion._content) > 0:
            try:
                contenido = json.loads(str(peticion._content, 'utf-8'))
            except json.JSONDecodeError:
                return

            self.sudo().env.company.ultima_respuesta_exo = ultimo_mensaje

            if 'identificacion' in contenido:
                if self.vat != contenido.get('identificacion'):
                    raise UserError(_('El código de exoneración no concuerda con la cédula del socio de negocio.'))
                
                # Fecha de emisión
                if contenido.get('fechaEmision'):
                    try:
                        fecha_emision = datetime.strptime(str(contenido.get('fechaEmision'))[:10], '%Y-%m-%d')
                        self.date_issue = fecha_emision
                    except ValueError:
                        pass
                
                # Fecha de vencimiento
                if contenido.get('fechaVencimiento'):
                    try:
                        fecha_vencimiento = datetime.strptime(str(contenido.get('fechaVencimiento'))[:10], '%Y-%m-%d')
                        self.date_expiration = fecha_vencimiento
                    except ValueError:
                        pass
                
                # Porcentaje de exoneración
                if contenido.get('porcentajeExoneracion'):
                    self.percentage_exoneration = float(contenido.get('porcentajeExoneracion'))
                
                # Número de Autorizacion Exoneracion
                if contenido.get('autorizacion'):
                    self.authorization_exoneration = str(contenido.get('autorizacion'))
                
                # Institución
                if contenido.get('nombreInstitucion'):
                    # Buscar institución por nombre o código
                    institution = self.env['institution.exoneration'].search([
                        '|',
                        ('name', 'ilike', contenido.get('nombreInstitucion')),
                        ('code', '=', contenido.get('codigoInstitucion', ''))
                    ], limit=1)
                    if institution:
                        self.institution_id = institution.id
                    else:
                        # Fallback al campo legacy
                        self.institution_name = contenido.get('nombreInstitucion')
                
                # Códigos CABYS autorizados
                if contenido.get('cabys'):
                    self.allowed_cabys_ids = [(0, 0, {'name': code}) for code in contenido.get('cabys')]

                # Tipo de documento
                tipo_documento = contenido.get('tipoDocumento')
                if tipo_documento:
                    autorizacion = self.env['aut.ex'].sudo().search([
                        ('code', '=', tipo_documento.get('codigo')),
                        ('active', '=', True)
                    ], limit=1)

                    if autorizacion:
                        self.type_exoneration = autorizacion.id

    def check_exonerations(self):
        """Verificar exoneraciones vencidas y enviar notificaciones"""
        clients = self.env["res.partner"].search([
            ("has_exoneration", "=", True),
            ("date_expiration", "<", datetime.today())
        ])
        for client in clients:
            if not client.date_notification or (client.date_notification + timedelta(days=8)) < date.today():
                email_template = client.env.ref("cr_electronic_invoice.email_template_client_exoneration_expired", False)
                if email_template:
                    email_template.send_mail(client.id)
                    client.date_notification = date.today()

    # ==============================================================================================
    #                          WRITE METHOD
    # ==============================================================================================

    def write(self, vals):
        _logger.debug('res.partner write vals: %s', vals)
        return super(PartnerElectronic, self).write(vals)

    # ==============================================================================================
    #                          HELPER METHODS FOR XML GENERATION
    # ==============================================================================================

    def get_exoneration_data_for_xml(self):
        """
        Retornar datos de exoneración formateados para generación de XML.
        
        Returns:
            dict: Datos de exoneración o False si no tiene exoneración
        """
        self.ensure_one()
        
        if not self.has_exoneration:
            return False
        
        data = {
            'tipo_documento_ex': self.type_exoneration.code if self.type_exoneration else '',
            'tipo_documento_otro': self.type_exoneration_other if self.requires_type_other else '',
            'numero_documento': self.exoneration_number or '',
            'articulo': str(self.exoneration_article) if self.exoneration_article else '',
            'inciso': str(self.exoneration_inciso) if self.exoneration_inciso else '',
            'nombre_institucion': self.institution_id.code if self.institution_id else (self.institution_name or ''),
            'nombre_institucion_otros': self.institution_name_other if self.requires_institution_other else '',
            'fecha_emision_ex': self.date_issue.strftime('%Y-%m-%dT00:00:00-06:00') if self.date_issue else '',
            'tarifa_exonerada': f"{self.percentage_exoneration:.2f}" if self.percentage_exoneration else '0.00',
        }
        
        return data