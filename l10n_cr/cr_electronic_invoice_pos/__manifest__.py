{
    'name': 'Facturación electrónica Costa Rica POS',
    'version': '19.0.0.1.0',
    'author': 'Odoo Community OpenCR, ABChainD Sys',
    'maintainer': 'RubenMT',
    'website': 'https://codeberg.org/OpenCR/l10n_cr',
    'category': 'Account',
    'description': """
        Costa Rica Electronic Invoicing Module for Odoo POS
        
        Features:
        - Electronic invoice generation (FE, TE, NC)
        - Exoneration support for eligible customers
        - CABYS product codes integration
        - Tax calculations with exoneration
    """,
    'depends': [
        'cr_electronic_invoice',
        'point_of_sale',
        'l10n_cr_hacienda_info_query',
    ],
    'data': [
        'data/res.partner.csv',
        'views/res_config_settings_view.xml',
        'views/pos_payment_method_form.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            # Core models (existing)
            'cr_electronic_invoice_pos/static/src/js/models.js',
            'cr_electronic_invoice_pos/static/src/js/pos_order_exoneration.js',
            'cr_electronic_invoice_pos/static/src/js/discount_code_popup.js',
            'cr_electronic_invoice_pos/static/src/js/control_buttons.js',
            'cr_electronic_invoice_pos/static/src/js/payment_screen.js',
            # XML templates (existing)
            'cr_electronic_invoice_pos/static/src/xml/control_buttons.xml',
            'cr_electronic_invoice_pos/static/src/xml/credit_note_popup.xml',
            'cr_electronic_invoice_pos/static/src/xml/discount_code_popup.xml',
            # Credit note popup (existing)
            'cr_electronic_invoice_pos/static/src/js/credit_note_popup.js',
            # Exoneration support
            'cr_electronic_invoice_pos/static/src/js/pos_store_exoneration.js',
            'cr_electronic_invoice_pos/static/src/js/payment_screen_exoneration.js',
            'cr_electronic_invoice_pos/static/src/js/exoneration_info_popup.js',
            'cr_electronic_invoice_pos/static/src/xml/exoneration_info_popup.xml',
            # Exoneration UI in payment screen
            'cr_electronic_invoice_pos/static/src/xml/exoneration_payment_screen.xml',
            # Receipt with exoneration
            'cr_electronic_invoice_pos/static/src/xml/custom_orderReceipt.xml',
            'cr_electronic_invoice_pos/static/src/xml/order_receipt_exoneration.xml',
        ],
    },
    'installable': True,
}