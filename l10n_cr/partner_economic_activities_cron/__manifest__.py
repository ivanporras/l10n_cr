{
    'name': 'Partner Economic Activities Cron',
    'version': '19.0.0.0.0',
    'author': 'Singulary, ABChainD Sys',
    'license': 'AGPL-3',
    'website': 'https://singulary.online',
    'category': 'Accounting/Accounting',
    'description':
        '''

                       Programa un cron para ejecutar action_get_economic_activities en contactos sin actividades economicas
                        ''',
    'depends': [
        'cr_electronic_invoice'
    ],
    'data': [
        "data/ir_cron.xml"
    ],
    'installable': True,
    'application': False,
    'maintainer': 'OdooFeCR,Singulary, RubenMT',
    'support': 'https://codeberg.org/OpenCR/l10n_cr/issues'
}