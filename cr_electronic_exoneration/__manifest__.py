{
    'name': 'Costa Rica - Exoneraciones Electrónicas',
    'version': '17.0.1.1.0',
    'category': 'Accounting/Localizations',
    'summary': 'Sistema avanzado de exoneraciones múltiples para Costa Rica',
    'description': '''
        Sistema completo de exoneraciones para Costa Rica que permite:
        • Múltiples exoneraciones por cliente
        • Consulta automática a APIs de Hacienda
        • Cálculo inteligente de impuestos con exoneración
        • Integración completa con facturación electrónica
        • Visualización de montos exonerados en facturas
        • Interfaz intuitiva y moderna
    ''',
    'author': 'Tech Consulting Services',
    'website': 'https://www.techconsultingservices.net',
    'developer': 'Bryan Soto Barquero',
    'depends': [
        'base',
        'account',
        'cr_electronic_invoice',
        'cabys',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/exoneration_institution_data.xml',
        'data/exoneration_type_data.xml',
        'views/exoneration_cabys_line_views.xml',
        'views/exoneration_institution_views.xml',
        'views/exoneration_type_views.xml',
        'views/partner_exoneration_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'views/sale_order_report_templates.xml',
        'views/account_invoice_report_templates.xml',
        'views/menuitems.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}