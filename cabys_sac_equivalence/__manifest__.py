{
    'name': 'Equivalencias SAC - CABYS',
    'summary': 'Mapa de equivalencias entre SAC versión 2017 y Cabys',
    'version': '19.0.1.0.0',
    'author': 'SNG, info@sngcloud.com, ABChainD Sys',
    'maintainer': 'RubenMT',
    'license': 'AGPL-3',
    'category': 'Accounting',
    'website': '',
    'depends': [
        'cabys',
        'stock',
    ],
    'data': [
        'data/ir_config_parameter.xml',
        'security/ir.model.access.csv',
        'views/sac_equivalence_views.xml',
        'wizard/sac_import_wizard.xml',
        'views/product_template_views.xml',
        'wizard/sac_config_wizard.xml',
        'views/res_config_settings_stock_views.xml',
    ],
    'external_dependencies': {
        'python': [
            'pandas',
            'openpyxl',
        ]
    },
    'installable': True,
}
