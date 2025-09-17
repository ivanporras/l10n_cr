from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ==============================================================================================
    #                                    NUEVAS EXONERACIONES
    # ==============================================================================================

    # Mantener compatibilidad con sistema anterior
    has_exoneration_new = fields.Boolean(
        string="Tiene Exoneraciones",
        help="Activa el nuevo sistema de exoneraciones múltiples"
    )

    exoneration_ids = fields.One2many(
        comodel_name='res.partner.exoneration',
        inverse_name='partner_id',
        string='Exoneraciones'
    )

    exoneration_count = fields.Integer(
        string='Cantidad de Exoneraciones',
        compute='_compute_exoneration_count',
        store=True
    )

    active_exonerations_count = fields.Integer(
        string='Exoneraciones Activas',
        compute='_compute_exoneration_count',
        store=True
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('exoneration_ids', 'exoneration_ids.active', 'exoneration_ids.date_expiration')
    def _compute_exoneration_count(self):
        for partner in self:
            partner.exoneration_count = len(partner.exoneration_ids)

            # Contar solo exoneraciones activas y vigentes
            active_exonerations = partner.exoneration_ids.filtered(
                lambda e: e.active and e.is_valid_today()
            )
            partner.active_exonerations_count = len(active_exonerations)

    # -------------------------------------------------------------------------
    # BUSINESS METHODS
    # -------------------------------------------------------------------------

    def get_applicable_exoneration(self, cabys_code):
        """
        ✅ MEJORADO: Encuentra exoneración específica para un código CABYS con logs
        """
        if not self.has_exoneration_new or not cabys_code:
            return False

        # 🔍 LOGS DE DEBUGGING
        _logger.info(f"🔍 Buscando exoneración para código: {cabys_code}")
        _logger.info(f"👤 Cliente: {self.name}")

        # Buscar exoneraciones activas y vigentes
        active_exonerations = self.exoneration_ids.filtered(
            lambda e: e.active and e.is_valid_today()
        )

        _logger.info(f"📋 Exoneraciones activas: {len(active_exonerations)}")

        # Buscar exoneración que contenga el código CABYS específico
        for exoneration in active_exonerations:
            _logger.info(f"🔍 Verificando exoneración: {exoneration.exoneration_number}")
            _logger.info(f"   🏷️ Códigos CABYS: {exoneration.cabys_count}")

            if exoneration.has_cabys_code(cabys_code):
                _logger.info(f"✅ CÓDIGO CABYS ENCONTRADO en {exoneration.exoneration_number}")
                return exoneration
            else:
                _logger.info(f"❌ Código {cabys_code} NO está en {exoneration.exoneration_number}")

        _logger.info(f"❌ No se encontró exoneración para código: {cabys_code}")
        return False

    def action_view_exonerations(self):
        """Acción para ver todas las exoneraciones del cliente"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Exoneraciones - {self.name}',
            'res_model': 'res.partner.exoneration',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
            'target': 'current',
        }

    def migrate_old_exonerations(self):
        """
        Migra exoneraciones del sistema anterior al nuevo sistema
        """
        if not self.has_exoneration or self.has_exoneration_new:
            return

        # Crear exoneración desde datos antiguos
        if self.exoneration_number:
            exoneration_data = {
                'partner_id': self.id,
                'exoneration_number': self.exoneration_number,
                'percentage_exoneration': self.percentage_exoneration or 0.0,
                'date_issue': self.date_issue,
                'date_expiration': self.date_expiration,
                'institution_name': self.institution_name or 'Sin especificar',
                'description': 'Migrado desde sistema anterior',
            }

            # Buscar institución y tipo por nombre
            if self.type_exoneration:
                exoneration_data['exoneration_type_id'] = self.type_exoneration.id

            new_exoneration = self.env['res.partner.exoneration'].create(exoneration_data)

            # Migrar códigos CABYS si existen
            if self.allowed_cabys_ids:
                cabys_lines = []
                for cabys in self.allowed_cabys_ids:
                    cabys_lines.append((0, 0, {
                        'cabys_code': cabys.name,
                        'description': f'Código {cabys.name}'
                    }))

                if cabys_lines:
                    cabys_set = self.env['exoneration.cabys.set'].create({
                        'exoneration_number': self.exoneration_number,
                        'cabys_line_ids': cabys_lines
                    })
                    new_exoneration.cabys_set_id = cabys_set.id

            # Activar nuevo sistema
            self.has_exoneration_new = True

            _logger.info(f'Exoneración migrada para cliente {self.name}: {self.exoneration_number}')