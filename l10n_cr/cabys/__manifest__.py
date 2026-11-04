{
    'name': "Catálogo de bienes y servicios para uso tributario y Cuentas Nacionales",

    'summary': "Catálogo de bienes y servicios para uso tributario y Cuentas Nacionales",
    'author': 'Singulary,info@fakturacion.com,ABChainD Sys',
    'maintainer': 'RubenMT',
    'website': "",
    'category': 'Account',
    'version': '19.0.1.0.0',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'account',
        'product',
    ],
    'data': [
        'views/cabys_producto_views.xml',
        'data/pharmaceutical_forms_data.xml',
        'views/pharmaceutical_form_views.xml',
        'views/cabys_views.xml',
        'views/product_product_views.xml',
        'views/product_template_views.xml',
        'views/product_category_views.xml',
        'views/res_company_views.xml',
        'wizard/cabys_catalog_import_wizard.xml',
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'web.core',
            'web.ListController',
      ],
        'web.assets_qweb': [
            'cabys/static/src/xml/cabys_templates.xml',
        ]
    },
    'external_dependencies': {
        "python": [
            'pandas',
            'openpyxl',
        ],
    },
    'installable': True,
}
