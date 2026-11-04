{
    'name': 'Instalador de FE CR',
    'version': '19.0.0.1.0',
    'author': 'OdooFeCR,Singulary,OpenCR(ripchaos),ABChainD Sys', 
    'license': 'AGPL-3',
    'website': 'https://singulary.online',
    'category': 'Accounting/Accounting',
    'description':
        '''
        Instalador completo para Facturación Electrónica de Costa Rica.
        
        Este módulo instala automáticamente todos los componentes necesarios para la
        facturación electrónica en Costa Rica, incluyendo:
        - Facturación electrónica base
        - Catálogo de bienes y servicios (CABYS)
        - Importación de facturas de proveedores
        - Reportes QWeb para facturación electrónica
        - Reportes financieros
        - Rangos de fechas
        - Reportes en Excel
        
        Todos los módulos dependientes están incluidos en esta instalación.
        ''',
    'depends': [
        'cr_electronic_invoice',
        'cabys',
        'cr_import_vendor_bills',
        'cr_electronic_invoice_qweb_fe',
        'account_financial_report',
        'date_range',
        'report_xlsx',
        'l10n_cr_hacienda_info_query'
        ],
    'auto_install': False,
    'sequence': 1,
    'post_init_hook': 'post_install_hook',
    'data': [
        'security/ir.model.access.csv',
        'data/cr_electronic_invoice_data.xml',
        'views/cr_electronic_invoice_install_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {},
    'external_dependencies': {
        "python": [
            'cryptography',
            'phonenumbers',
            'jsonschema',
        ],
    },
    'installable': True,
    'application': True,
    'summary': 'Instalador completo para Facturación Electrónica de Costa Rica',
    'images': ['static/description/banner.svg', 'static/description/icon.png'],
    'maintainer': 'OdooFeCR,Singulary,RubenMT',
    'support': 'https://codeberg.org/OpenCR/l10n_cr/issues'
}
