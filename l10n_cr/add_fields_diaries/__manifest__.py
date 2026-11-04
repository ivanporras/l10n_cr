# -*- coding: utf-8 -*-
# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Agregar campos a FE Diarios',
    'version': '19.0.0.0.0',
    'category': 'Account',
    'author': "Carlos Wong, Akurey S.A, Singulary, ABChainD Sys",
    'maintainer': 'RubenMT',
    'website': 'www.singulary.online',
    'license': 'AGPL-3',
    'depends': ['cr_electronic_invoice'],
    'data': [
        'views/account_journal_view.xml',
        'views/account_move_view.xml',

    ],
    'installable': True,
    'auto_install': False,
}
