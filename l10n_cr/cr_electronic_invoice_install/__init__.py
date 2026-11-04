# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID
from . import models
from .models.post_install import CrElectronicInvoiceInstall

def post_install_hook(env):
    """Hook que se ejecuta después de instalar el módulo"""
    # Asegurarse de que el modelo existe antes de llamarlo
    if 'cr.electronic.invoice.install' in env:
        return env['cr.electronic.invoice.install'].post_install_hook(env.registry)
    return True