# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartnerOtroTextoRule(models.Model):
    _name = "res.partner.otro.texto.rule"
    _description = "Reglas de OtroTexto para Factura Electrónica por Cliente"
    _order = "sequence, partner_id"

    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one(
        "res.partner", string="Cliente", required=True, ondelete="cascade"
    )

    codigo = fields.Char(
        string="Código del nodo",
        help="El valor para el atributo 'codigo' en la etiqueta <OtroTexto>. "
        "Déjelo en blanco si no se requiere un código.",
    )
    
    xml_node_type = fields.Selection(
        [("text", "Otro Texto"), ("content", "Otro Contenido")],
        string="Tipo de Nodo XML",
        required=True,
        default="text",
        help="Seleccione si se generará una etiqueta <OtroTexto> o <OtroContenido>. El estándar XSD requiere que todos los OtroTexto aparezcan antes que OtroContenido."
    )

    source_type = fields.Selection(
        [("free_text", "Texto Libre"), ("field", "Campo de Factura")],
        string="Tipo de Origen",
        required=True,
        default="free_text",
    )

    value_field_id = fields.Many2one(
        "ir.model.fields",
        string="Campo de Factura",
        domain="[('model', '=', 'account.move'), ('store', '=', True), ('ttype', 'not in', ['binary', 'one2many', 'many2many'])]",
        help="Seleccione un campo del modelo de factura (account.move) para obtener el valor.",
    )

    value_free_text = fields.Char(
        string="Valor (Texto Libre)", help="Escriba el valor estático que se usará."
    )

    @api.onchange('source_type')
    def _onchange_source_type(self):
        """
        Limpia el campo de valor que no corresponde al tipo de origen seleccionado,
        mejorando la experiencia de usuario y evitando datos inconsistentes.
        """
        if self.source_type == 'free_text':
            self.value_field_id = False
        elif self.source_type == 'field':
            self.value_free_text = ''