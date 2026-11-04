# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Importador de Facturas de Proveedores',
    'version': '19.0.0.0.0',
    'category': 'Vendor Bills',
    'author': 'OdooFeCR, ABChainD Sys',
    'maintainer': 'RubenMT',
    'license': 'AGPL-3',
    'website': '',
    'summary': 'Importación automática de facturas de proveedores desde el servidor de correo.',

    'description': """
        Este módulo permite la importación y procesamiento automático de facturas de proveedores (XML v4.3/v4.4) 
        recibidas por correo electrónico, facilitando el registro de documentos de compra en Odoo para la 
        localización de Costa Rica.
    """,

    # any module necessary for this one to work correctly
    'depends': ['cr_electronic_invoice', 'mail'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/res_company_views.xml',
        'views/account_move.xml',
        'wizard/cr_multiple_invoice_validation_wz_view.xml',
    ],
    'installable': True,


}
