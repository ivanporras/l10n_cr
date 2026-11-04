from odoo import models, api
import re


class CabysProductoInherit(models.Model):
    _inherit = 'cabys.producto'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        """Permite buscar cabys.producto también por código SAC equivalente.
        Si el usuario escribe un código SAC, se buscan equivalencias y se
        incluyen los productos CABYS relacionados en el dominio de búsqueda.
        """
        domain = domain or []

        if name:
            # Base logic: look for name/code
            # We explicitly define this because we are adding the SAC logic via OR
            name_domain = ['|', ('name', operator, name), ('codigo', operator, name)]
            
            # SAC equivalence logic
            clean = re.sub(r"\D", "", name)
            eqrecs = self.env['cabys.sac.equivalence'].sudo().search([
                '|', ('sac_code', operator, name), ('sac_code_clean', operator, clean)
            ], limit=limit)
            
            sac_ids = eqrecs.mapped('cabys_product_id').ids
            
            if sac_ids:
                # Combine base_domain OR sac_domain
                name_domain = ['|'] + name_domain + [('id', 'in', sac_ids)]
            
            # Combine with incoming domain (usually filters)
            if domain:
                domain = [('&')] + domain + name_domain
            else:
                domain = name_domain

        return self._search(domain, limit=limit, order=order)
