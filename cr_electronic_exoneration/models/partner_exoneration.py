import re

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, datetime, timedelta
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class PartnerExoneration(models.Model):
    _name = 'res.partner.exoneration'
    _description = 'Exoneración de Cliente'
    _order = 'date_expiration desc, exoneration_number'
    _rec_name = 'display_name'

    # ==============================================================================================
    #                                      CAMPOS PRINCIPALES
    # ==============================================================================================

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        required=True,
        ondelete='cascade'
    )

    exoneration_number = fields.Char(
        string='Número de Exoneración',
        required=True,
        help='Número oficial de la exoneración otorgada por la institución'
    )

    institution_id = fields.Many2one(
        comodel_name='exoneration.institution',
        string='Institución Emisora'
    )

    institution_name = fields.Char(
        string='Nombre Institución',
        help='Nombre de la institución (se llena automáticamente desde institución o manualmente)'
    )

    exoneration_type_id = fields.Many2one(
        comodel_name='exoneration.type',
        string='Tipo de Exoneración'
    )

    percentage_exoneration = fields.Float(
        string='Porcentaje de Exoneración (%)',
        required=True,
        help='Porcentaje de IVA exonerado (ej: 13 para 13%)'
    )

    date_issue = fields.Date(
        string='Fecha de Emisión',
        required=True,
        default=fields.Date.context_today  # ✅ AGREGADO: Valor por defecto
    )

    date_expiration = fields.Date(
        string='Fecha de Vencimiento',
        required=True
    )

    active = fields.Boolean(
        string='Activa',
        default=True
    )

    description = fields.Text(
        string='Descripción'
    )

    # ==============================================================================================
    #                                      CÓDIGOS CABYS
    # ==============================================================================================

    cabys_set_id = fields.Many2one(
        comodel_name='exoneration.cabys.set',
        string='Códigos CABYS',
        help='Conjunto de códigos CABYS permitidos para esta exoneración'
    )

    cabys_line_ids = fields.One2many(
        related='cabys_set_id.cabys_line_ids',
        string='Líneas de Códigos CABYS',
        readonly=True
    )

    cabys_count = fields.Integer(
        string='Cantidad de Códigos CABYS',
        compute='_compute_cabys_count',
        store=True
    )

    # ==============================================================================================
    #                                      CAMPOS CALCULADOS
    # ==============================================================================================

    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name'
    )

    days_to_expiry = fields.Integer(
        string='Días para Vencimiento',
        compute='_compute_days_to_expiry',
        store=True
    )

    state = fields.Selection([
        ('active', 'Activa'),
        ('expiring', 'Por Vencer'),
        ('expired', 'Vencida'),
        ('inactive', 'Inactiva')
    ], string='Estado', compute='_compute_state', store=True)

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('cabys_set_id', 'cabys_set_id.cabys_line_ids')
    def _compute_cabys_count(self):
        for record in self:
            if record.cabys_set_id and record.cabys_set_id.cabys_line_ids:
                record.cabys_count = len(record.cabys_set_id.cabys_line_ids)
            else:
                record.cabys_count = 0

    @api.depends('exoneration_number', 'partner_id.name', 'percentage_exoneration')
    def _compute_display_name(self):
        for record in self:
            if record.exoneration_number and record.partner_id:
                record.display_name = f"{record.exoneration_number} - {record.percentage_exoneration}%"
            else:
                record.display_name = record.exoneration_number or 'Nueva Exoneración'

    @api.depends('date_expiration')
    def _compute_days_to_expiry(self):
        today = date.today()
        for record in self:
            if record.date_expiration:
                delta = record.date_expiration - today
                record.days_to_expiry = delta.days
            else:
                record.days_to_expiry = 0

    @api.depends('active', 'date_expiration')
    def _compute_state(self):
        today = date.today()
        for record in self:
            if not record.active:
                record.state = 'inactive'
            elif record.date_expiration and record.date_expiration < today:
                record.state = 'expired'
            elif record.date_expiration and (record.date_expiration - today).days <= 30:
                record.state = 'expiring'
            else:
                record.state = 'active'

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.onchange('exoneration_number')
    def _onchange_exoneration_number(self):
        """✅ MEJORADO CON LOGS DE DEBUGGING"""
        if not self.exoneration_number or len(self.exoneration_number.strip()) < 8:
            return

        # 🔍 LOGS DE DEBUGGING
        _logger.info("=" * 60)
        _logger.info("🔍 DEBUG ONCHANGE EXONERATION NUMBER")
        _logger.info("=" * 60)
        _logger.info(f"📋 Número ingresado: {self.exoneration_number}")
        _logger.info(f"📊 Cabys existentes: {self.cabys_count}")
        _logger.info(f"🎯 Cabys set ID: {self.cabys_set_id}")

        # ✅ CORREGIDO: Solo cargar si no hay códigos CABYS existentes
        if not self.cabys_set_id or self.cabys_count == 0:
            _logger.info("🚀 Iniciando carga automática desde Hacienda...")
            self._load_cabys_from_hacienda()
        else:
            _logger.info("ℹ️ Ya existen códigos CABYS, mostrando advertencia")
            return {
                'warning': {
                    'title': _('Códigos CABYS Existentes'),
                    'message': _('Ya existen códigos CABYS para esta exoneración. '
                                 'Use el botón "Recargar desde Hacienda" si desea actualizarlos.'),
                }
            }

    @api.onchange('institution_id')
    def _onchange_institution_id(self):
        """Sincroniza el nombre de la institución"""
        if self.institution_id:
            self.institution_name = self.institution_id.name

    # ✅ NUEVO: Recalcular campos al cambiar fechas
    @api.onchange('date_expiration', 'active')
    def _onchange_compute_fields(self):
        """Recalcula campos computed cuando cambian dependencias"""
        self._compute_days_to_expiry()
        self._compute_state()

    # -------------------------------------------------------------------------
    # CONSTRAINT METHODS
    # -------------------------------------------------------------------------

    @api.constrains('percentage_exoneration')
    def _check_percentage_exoneration(self):
        """✅ VALIDACIÓN CORREGIDA CON LOGS DE DEBUGGING"""
        for record in self:
            # 🔍 LOGS DE DEBUGGING
            _logger.info("=" * 60)
            _logger.info("🔍 DEBUG VALIDACIÓN DE PORCENTAJE")
            _logger.info("=" * 60)
            _logger.info(f"📋 Exoneración: {record.exoneration_number}")
            _logger.info(f"📊 Porcentaje recibido: {record.percentage_exoneration}")
            _logger.info(f"📈 Tipo de dato: {type(record.percentage_exoneration)}")

            # Validar que no sea negativo
            if record.percentage_exoneration < 0:
                _logger.error(f"❌ Porcentaje negativo: {record.percentage_exoneration}")
                raise ValidationError(_('El porcentaje de exoneración no puede ser negativo'))

            # ✅ LÓGICA CORREGIDA: Validar rangos apropiados
            is_decimal_format = 0 <= record.percentage_exoneration <= 1  # 0.12 para 12%
            is_integer_format = 1 < record.percentage_exoneration <= 100  # 12 para 12%
            is_zero_percent = record.percentage_exoneration == 0  # 0% válido

            _logger.info(f"🔢 Es formato decimal (0-1): {is_decimal_format}")
            _logger.info(f"🔢 Es formato entero (1-100): {is_integer_format}")
            _logger.info(f"🔢 Es cero por ciento: {is_zero_percent}")

            if not (is_decimal_format or is_integer_format or is_zero_percent):
                _logger.error(f"❌ Porcentaje inválido: {record.percentage_exoneration}")
                _logger.error(f"❌ No cumple ningún formato válido")
                raise ValidationError(_(
                    'El porcentaje de exoneración debe estar entre 0% y 100%. '
                    'Formatos válidos: 0.12 (decimal) o 12 (entero) para 12%'
                ))

            _logger.info(f"✅ Porcentaje válido: {record.percentage_exoneration}")
            _logger.info("=" * 60)

    @api.constrains('date_issue', 'date_expiration')
    def _check_dates(self):
        for record in self:
            if record.date_issue and record.date_expiration:
                if record.date_issue > record.date_expiration:
                    raise ValidationError(_('La fecha de emisión no puede ser posterior a la fecha de vencimiento'))

    @api.constrains('exoneration_number', 'partner_id')
    def _check_unique_exoneration_number(self):
        for record in self:
            if record.exoneration_number:
                duplicates = self.search([
                    ('id', '!=', record.id),
                    ('exoneration_number', '=', record.exoneration_number),
                    ('partner_id', '=', record.partner_id.id)
                ])
                if duplicates:
                    raise ValidationError(
                        _('Ya existe una exoneración con el número %s para este cliente') %
                        record.exoneration_number
                    )

    # -------------------------------------------------------------------------
    # BUSINESS METHODS
    # -------------------------------------------------------------------------

    def is_valid_today(self):
        """Verifica si la exoneración está vigente hoy"""
        self.ensure_one()
        today = date.today()
        return (
                self.active and
                self.date_expiration and
                self.date_expiration >= today
        )

    def has_cabys_code(self, cabys_code):
        """
        Verifica si esta exoneración incluye un código CABYS específico

        Args:
            cabys_code (str): Código CABYS a verificar

        Returns:
            bool: True si el código está incluido
        """
        self.ensure_one()
        if not self.cabys_set_id or not cabys_code:
            return False

        return bool(self.cabys_set_id.cabys_line_ids.filtered(
            lambda line: line.cabys_code == cabys_code
        ))

    def _parse_api_date(self, date_string):
        """
        ✅ NUEVO: Parsea fechas de la API manejando diferentes formatos

        Args:
            date_string (str): Fecha en formato ISO o similar

        Returns:
            date: Objeto fecha de Python
        """
        if not date_string:
            return False

        try:
            # Remover timezone info si existe y parsear
            date_clean = str(date_string).replace('T00:00:00', '').split('T')[0]
            return datetime.strptime(date_clean, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
            _logger.warning(f'Error parseando fecha {date_string}: {e}')
            return False

    def _load_cabys_from_hacienda(self):
        """✅ MEJORADO CON LOGS DETALLADOS DE LA API"""
        if not self.exoneration_number:
            return False

        try:
            # 🔍 LOGS DE DEBUGGING
            _logger.info("=" * 80)
            _logger.info("🌐 DEBUG CONSULTA API HACIENDA")
            _logger.info("=" * 80)
            _logger.info(f"📋 Número de exoneración: {self.exoneration_number}")

            # Obtener URL base de configuración
            url_base = self.env.company.url_base_exo
            if not url_base:
                _logger.error('❌ URL base de exoneraciones no configurada')
                return False

            url_base = url_base.strip()
            if url_base.endswith('/'):
                url_base = url_base[:-1]

            endpoint = f"{url_base}autorizacion={self.exoneration_number}"
            _logger.info(f"🌐 URL de consulta: {endpoint}")

            headers = {'content-type': 'application/json'}

            # Realizar consulta
            response = requests.get(endpoint, headers=headers, timeout=10)
            _logger.info(f"📡 Status Code: {response.status_code}")
            _logger.info(f"📏 Content Length: {len(response.content)}")

            if response.status_code in (200, 202) and len(response.content) > 0:
                data = json.loads(response.content.decode('utf-8'))

                # 🔍 LOGS DETALLADOS DE LA RESPUESTA
                _logger.info("📦 DATOS RECIBIDOS DE LA API:")
                _logger.info(f"🆔 Identificación: {data.get('identificacion', 'N/A')}")
                _logger.info(f"📅 Fecha Emisión: {data.get('fechaEmision', 'N/A')}")
                _logger.info(f"📅 Fecha Vencimiento: {data.get('fechaVencimiento', 'N/A')}")
                _logger.info(f"🏛️ Nombre Institución: {data.get('nombreInstitucion', 'N/A')}")

                # ⚠️ PUNTO CRÍTICO: Procesar porcentaje
                if 'porcentajeExoneracion' in data:
                    percentage_from_api = data.get('porcentajeExoneracion')
                    _logger.info(f"📊 PORCENTAJE DESDE API (RAW): {percentage_from_api}")
                    _logger.info(f"📊 Tipo de dato API: {type(percentage_from_api)}")

                    # Convertir a float y dividir entre 100
                    percentage_float = float(percentage_from_api)
                    percentage_decimal = percentage_float / 100

                    _logger.info(f"📊 Porcentaje float: {percentage_float}")
                    _logger.info(f"📊 Porcentaje decimal (final): {percentage_decimal}")

                    # ⚠️ ASIGNACIÓN CRÍTICA
                    self.percentage_exoneration = percentage_decimal
                    _logger.info(f"✅ Porcentaje asignado al campo: {self.percentage_exoneration}")

                # Validar identificación del cliente
                if 'identificacion' in data and self.partner_id and self.partner_id.vat:
                    if self.partner_id.vat != data.get('identificacion'):
                        _logger.warning(
                            f'⚠️ Identificación no coincide: {self.partner_id.vat} vs {data.get("identificacion")}')

                # Procesar fechas
                if 'fechaEmision' in data:
                    parsed_date = self._parse_api_date(data.get('fechaEmision'))
                    if parsed_date:
                        self.date_issue = parsed_date
                        _logger.info(f"📅 Fecha emisión asignada: {self.date_issue}")

                if 'fechaVencimiento' in data:
                    parsed_date = self._parse_api_date(data.get('fechaVencimiento'))
                    if parsed_date:
                        self.date_expiration = parsed_date
                        _logger.info(f"📅 Fecha vencimiento asignada: {self.date_expiration}")

                # Procesar institución
                if 'nombreInstitucion' in data:
                    institution_name = data.get('nombreInstitucion')
                    self.institution_name = institution_name
                    _logger.info(f"🏛️ Institución asignada: {self.institution_name}")

                # Procesar códigos CABYS
                if 'cabys' in data and data['cabys'] and not self.cabys_set_id:
                    cabys_count = len(data['cabys'])
                    _logger.info(f"🏷️ Códigos CABYS encontrados: {cabys_count}")

                    cabys_lines = []
                    for cabys_code in data['cabys']:
                        cabys_lines.append((0, 0, {
                            'cabys_code': cabys_code,
                            'description': f'Código {cabys_code}'
                        }))
                        _logger.info(f"🏷️ Código CABYS: {cabys_code}")

                    if cabys_lines:
                        cabys_set = self.env['exoneration.cabys.set'].create({
                            'exoneration_number': self.exoneration_number,
                            'cabys_line_ids': cabys_lines
                        })
                        self.cabys_set_id = cabys_set.id
                        _logger.info(f"✅ Conjunto CABYS creado: {cabys_set.id}")

                _logger.info('✅ Códigos CABYS cargados automáticamente')
                _logger.info("=" * 80)
                return True

            else:
                _logger.error(f'❌ API response no válida: Status {response.status_code}')
                return False

        except requests.exceptions.RequestException as e:
            _logger.error(f'❌ Error consultando API de Hacienda: {e}')
            return False
        except Exception as e:
            _logger.error(f'❌ Error procesando respuesta de Hacienda: {e}')
            return False

    def action_view_cabys_codes(self):
        """Acción para ver los códigos CABYS de esta exoneración"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Códigos CABYS - {self.exoneration_number}',
            'res_model': 'exoneration.cabys.line',
            'view_mode': 'tree',
            'domain': [('cabys_set_id', '=', self.cabys_set_id.id)],
            'context': {
                'default_cabys_set_id': self.cabys_set_id.id,
                'create': False,
                'edit': False,
                'delete': False,
            },
            'target': 'new',
        }

    def action_reload_cabys(self):
        """
        ✅ MEJORADO: Acción para recargar códigos CABYS desde Hacienda
        """
        self.ensure_one()
        if not self.exoneration_number:
            raise UserError(_('Debe especificar el número de exoneración'))

        # Eliminar códigos existentes si los hay
        if self.cabys_set_id:
            self.cabys_set_id.unlink()
            self.cabys_set_id = False

        # Recargar desde Hacienda
        success = self._load_cabys_from_hacienda()

        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('Códigos CABYS recargados correctamente desde Hacienda'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Advertencia'),
                    'message': _('No se pudieron cargar los códigos CABYS desde Hacienda'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

    # ✅ NUEVO: Método para recalcular todos los campos computed
    def recompute_all_fields(self):
        """Recalcula todos los campos computed"""
        self._compute_cabys_count()
        self._compute_days_to_expiry()
        self._compute_state()
        self._compute_display_name()

    # ✅ NUEVO: Override create para asegurar campos computed
    @api.model
    def create(self, vals):
        """
        ✅ CORREGIDO: Override create para cargar códigos CABYS automáticamente
        """
        record = super().create(vals)

        # Si tiene número de exoneración pero no códigos CABYS, cargar automáticamente
        if record.exoneration_number and not record.cabys_set_id:
            try:
                record._load_cabys_from_hacienda()
            except Exception as e:
                _logger.warning(f'No se pudieron cargar códigos CABYS automáticamente: {e}')

        # Forzar recálculo después de crear
        record.recompute_all_fields()
        return record

    def write(self, vals):
        """
        ✅ CORREGIDO: Override write para cargar códigos CABYS automáticamente
        """
        result = super().write(vals)

        for record in self:
            # Si se actualizó el número de exoneración y no hay códigos CABYS
            if ('exoneration_number' in vals and record.exoneration_number and
                    not record.cabys_set_id):
                try:
                    record._load_cabys_from_hacienda()
                except Exception as e:
                    _logger.warning(f'No se pudieron cargar códigos CABYS automáticamente: {e}')

            # Si se actualizaron campos relevantes, recalcular
            if any(field in vals for field in ['date_expiration', 'active', 'cabys_set_id']):
                record.recompute_all_fields()

        return result