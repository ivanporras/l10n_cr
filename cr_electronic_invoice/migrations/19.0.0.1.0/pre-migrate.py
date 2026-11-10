# -*- coding: utf-8 -*-
# CAMBIO-31 Migración Odoo 17 -> 19
# Crea de antemano las columnas de los campos calculados/relacionados guardados
# (store=True) de cr_electronic_invoice. Si Odoo encuentra la columna ya creada,
# no la llena ni la recalcula para todos los registros de la tabla.
# Motivo: account_move tiene ~2.85 millones de asientos de todos los países; el
# llenado y recálculo tardaba más de una hora y terminaba agotando la memoria
# del servidor (odoo-bin process got killed).
# Los tipos coinciden con los que Odoo 19 usa para cada tipo de campo.
# Pendiente: calcular estos campos solo para las compañías de Costa Rica
# una vez que la base esté arriba.
import logging

_logger = logging.getLogger(__name__)

COLUMNAS = {
    "account_move": [
        ("amount_discount_electronic_invoice", "numeric"),
        ("amount_iva_returned", "numeric"),
        ("has_exoneration", "boolean"),
        ("exoneration_percentage", "double precision"),
        ("amount_exoneration", "numeric"),
        ("amount_tax_before_exoneration", "numeric"),
        ("amount_total_to_pay", "numeric"),
        ("partner_exoneration_number", "varchar"),
        ("partner_type_exoneration", "integer"),
        ("partner_exoneration_institution_id", "integer"),
        ("partner_exoneration_expiry", "date"),
        ("partner_vat", "varchar"),
        ("company_vat", "varchar"),
    ],
    "res_partner": [
        ("exoneration_article", "integer"),
        ("exoneration_inciso", "integer"),
        ("requires_article", "boolean"),
        ("requires_institution_other", "boolean"),
        ("requires_type_other", "boolean"),
    ],
}


def migrate(cr, version):
    creadas = []
    for tabla, columnas in COLUMNAS.items():
        for columna, tipo in columnas:
            cr.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                (tabla, columna),
            )
            if cr.fetchone():
                continue
            cr.execute(f'ALTER TABLE "{tabla}" ADD COLUMN "{columna}" {tipo}')
            creadas.append(f"{tabla}.{columna}")
    _logger.info(
        "CAMBIO-31: %s columna(s) creada(s) de antemano para evitar recálculo: %s",
        len(creadas), ", ".join(creadas) or "ninguna (ya existían)",
    )
