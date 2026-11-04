# -*- coding: utf-8 -*-
"""
POS Config Extension for Costa Rica Electronic Invoicing - Exoneration Support

This module extends pos.config to load partner exoneration data in POS frontend.
Simplified version - uses type_exoneration directly (no related field needed).
"""
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _description = 'Pos Config'
    _inherit = 'pos.config'

    default_partner_id = fields.Many2one(
        'res.partner',
        string='Cliente por defecto',
        help='Cliente que se seleccionará automáticamente al iniciar una orden'
    )

    def _load_pos_data_fields(self, config_id):
        """Extend to load exoneration fields for partners."""
        fields = super()._load_pos_data_fields(config_id)
        
        # Add exoneration fields to partner data loaded in POS
        if 'res.partner' in fields:
            partner_fields = fields['res.partner']
            exoneration_fields = [
                'has_exoneration',
                'percentage_exoneration',
                'type_exoneration',
                'exoneration_number',
                'date_expiration',
                'institution_name',
            ]
            for field in exoneration_fields:
                if field not in partner_fields:
                    partner_fields.append(field)
        
        return fields

    def _load_pos_data(self, config_id):
        """Override to add exoneration data for partners."""
        result = super()._load_pos_data(config_id)
        
        # Load allowed CABYS codes for partners with exoneration
        try:
            # Get all partners with exoneration
            partners_with_exoneration = self.env['res.partner'].search([
                ('has_exoneration', '=', True)
            ])
            
            # Load CABYS codes for these partners
            cabys_data = {}
            for partner in partners_with_exoneration:
                if partner.allowed_cabys_ids:
                    cabys_data[partner.id] = [line.name for line in partner.allowed_cabys_ids]
                else:
                    cabys_data[partner.id] = []
            
            # Add to result
            if '_extras' not in result:
                result['_extras'] = {}
            result['_extras']['partner_cabys_exoneration'] = cabys_data
            
            _logger.info(f"Loaded exoneration CABYS data for {len(cabys_data)} partners")
            
        except Exception as e:
            _logger.error(f"Error loading exoneration CABYS data: {e}")
        
        return result


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    @api.model
    def _load_pos_data_fields(self, config_id):
        """Load exoneration fields in POS for partners."""
        fields = super()._load_pos_data_fields(config_id)
        fields.extend([
            'has_exoneration',
            'percentage_exoneration',
            'type_exoneration',  # Direct field only - simplified
            'exoneration_number',
            'date_expiration',
            'institution_name',
        ])
        return fields
