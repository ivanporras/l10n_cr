#import base64
#import datetime
#import pytz

#import re
#from xml.sax.saxutils import escape
#from lxml import etree

from odoo import models, fields, api, _
from odoo.exceptions import UserError
#from odoo.tools.misc import get_lang
#from odoo.http import request
#from odoo.tools import html2plaintext

#from .qr_generator import GenerateQrCode
#from . import api_facturae
#from .. import extensions

#import logging
#_logger = logging.getLogger(__name__)

class AccountInvoiceElectronic(models.Model):
    _inherit = "account.move"

    show_cabys_codes_invoice_qweb = fields.Boolean(
        string="Show CABYS codes on invoice",
        default=False
        )

    def _get_name_invoice_report(self):
        """ This method need to be inherit by the localizations if they want to print a custom invoice report instead of
        the default one. For example please review the l10n_ar module """
        self.ensure_one()
        return 'cr_electronic_invoice_qweb_fe.report_invoice_document_fecr'
