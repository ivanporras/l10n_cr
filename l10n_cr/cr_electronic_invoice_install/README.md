# Instalador de Facturación Electrónica de Costa Rica

## Descripción

Este módulo es un instalador completo para la Facturación Electrónica de Costa Rica en Odoo 18. Instala automáticamente todos los componentes necesarios para cumplir con los requisitos de facturación electrónica establecidos por el Ministerio de Hacienda de Costa Rica.

## Características

- Instalación completa de todos los módulos necesarios para facturación electrónica
- Configuración automática de dependencias
- Incluye catálogo de bienes y servicios (CABYS)
- Soporte para importación de facturas de proveedores
- Reportes financieros integrados

## Módulos incluidos

Este instalador incluye los siguientes módulos:

- `cr_electronic_invoice`: Módulo principal de facturación electrónica
- `cabys`: Catálogo de bienes y servicios
- `cr_import_vendor_bills`: Importación de facturas de proveedores
- `account_financial_report`: Reportes financieros
- `date_range`: Rangos de fechas
- `report_xlsx`: Reportes en Excel

## Requisitos

- Odoo 18.0
- Python 3.8+
- Dependencias Python: cryptography, OpenSSL, phonenumbers, jsonschema

## Instalación

1. Asegúrese de que todas las dependencias Python estén instaladas:
   ```
   pip install cryptography OpenSSL phonenumbers jsonschema
   ```

2. Instale este módulo a través de la interfaz de Odoo:
   - Vaya a Aplicaciones
   - Busque "Instalador de FE CR"
   - Haga clic en Instalar

## Configuración

Después de la instalación, deberá configurar:

1. Datos de la compañía
2. Certificado digital para firma electrónica
3. Credenciales de acceso al API de Hacienda

## Soporte

Para soporte, por favor abra un issue en el repositorio GitHub: https://codeberg.org/OpenCR/l10n_cr/issues

## Autores

- OdooFeCR
- Singulary

## Licencia

AGPL-3