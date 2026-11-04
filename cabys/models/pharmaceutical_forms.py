from odoo import models, fields


class PharmaceuticalForm(models.Model):

    _name = 'pharmaceutical.form'

    _description = 'Pharmaceutical Form'


    code = fields.Char(string='Código', required=True)

    name = fields.Char(string='Forma Farmacéutica', required=True)


    _code_unique = models.Constraint('unique(code)', 'El código debe ser único.')