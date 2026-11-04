/** @odoo-module **/

import {patch} from "@web/core/utils/patch";
import {PaymentScreen} from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { CreditNotePopup } from "./credit_note_popup";

patch(OrderPaymentValidation.prototype, {
    shouldDownloadInvoice() {
        return false;
    },
});

/**
 * Get partner from order - handles both old and new Odoo 19 API
 */
function getPartnerFromOrder(order) {
    if (!order) return null;
    // Odoo 19: direct property access
    if (order.partner_id) {
        return order.partner_id;
    }
    // Odoo 19: try new method first
    if (typeof order.partner === 'function') {
        return order.partner();
    }
    // Fallback to old method
    if (typeof order.get_partner === 'function') {
        return order.get_partner();
    }
    // Direct access
    return order.partner || null;
}

/**
 * Set partner on order - handles Odoo 19 API
 */
function setPartnerOnOrder(order, partner) {
    if (!order || !partner) return;
    // Odoo 19: direct assignment to partner_id
    if ('partner_id' in order) {
        order.partner_id = partner;
    }
    // Fallback to old method
    else if (typeof order.set_partner === 'function') {
        order.set_partner(partner);
    }
}

/**
 * Get order lines - handles both old and new Odoo 19 API
 */
function getOrderlines(order) {
    if (!order) return [];
    // Odoo 19: try new method
    if (typeof order.get_orderlines === 'function') {
        return order.get_orderlines();
    }
    // Fallback: direct access to lines
    if (order.lines && Array.isArray(order.lines)) {
        return order.lines;
    }
    return [];
}

/**
 * Check if a partner has valid exoneration
 */
function hasValidExoneration(partner) {
    if (!partner) return false;
    if (!partner.has_exoneration) return false;
    
    if (partner.date_expiration) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const expirationDate = new Date(partner.date_expiration);
        if (expirationDate < today) return false;
    }
    
    const percentage = partner.percentage_exoneration || 0;
    return percentage > 0;
}

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = this.env.services.orm;
        this.dialog = this.env.services.dialog;
        this.tipo_documento = null;
    },

    /**
     * Override addNewPaymentLine to set exoneration-adjusted amount
     */
    async addNewPaymentLine(paymentMethod) {
        const order = this.currentOrder;
        const partner = getPartnerFromOrder(order);
        
        // Call original method first
        const result = await super.addNewPaymentLine(...arguments);
        
        // If exoneration applies, adjust the payment amount
        if (result && hasValidExoneration(partner)) {
            const adjustedTotal = order.get_total_with_tax();
            
            const paymentLines = this.paymentLines;
            if (paymentLines && paymentLines.length > 0) {
                const newPaymentLine = paymentLines[paymentLines.length - 1];
                if (newPaymentLine && newPaymentLine.set_amount) {
                    newPaymentLine.set_amount(adjustedTotal);
                    console.log("✅ Exoneration: Payment set to adjusted total:", adjustedTotal);
                }
            }
        }
        
        return result;
    },

    _showValidationErrorDialog(errorMessage, missingFields = []) {
        let body = errorMessage;
        
        if (missingFields && missingFields.length > 0) {
            const fieldList = missingFields.map(field => `  • ${field}`).join('\n');
            body = _t(
                "No se puede completar la operación.\n\n" +
                "Campos faltantes requeridos por Hacienda:\n" +
                "%s\n\n" +
                "Por favor complete la información del cliente antes de continuar."
            ).replace('%s', fieldList);
        }

        this.dialog.add(ConfirmationDialog, {
            title: _t("Error de Validación - Factura Electrónica"),
            body: body,
            confirmLabel: _t("Entendido"),
        });
    },

    async _validateOrderForFE() {
        // Odoo 19: use this.currentOrder instead of this.pos.get_order()
        const order = this.currentOrder;
        
        if (!this.pos.company.invoice_is_electronic) {
            return true;
        }

        // If no partner selected, use default partner from POS config
        let partnerId = order.partner_id?.id;
        if (!partnerId && this.pos.config.default_partner_id?.id) {
            partnerId = this.pos.config.default_partner_id.id;
            // Set the default partner on the order
            const defaultPartner = this.pos.models["res.partner"]?.get(partnerId);
            if (defaultPartner) {
                setPartnerOnOrder(order, defaultPartner);
                console.log("✅ Using default partner from POS config:", defaultPartner.name);
            }
        }

        const partnerIdToUse = order.partner_id?.id || this.pos.config.default_partner_id?.id;
        
        const orderlines = getOrderlines(order);
        const lineProductIds = orderlines
            .filter(line => {
                const product = line.product || (line.get_product && line.get_product());
                return product && product.id;
            })
            .map(line => {
                const product = line.product || (line.get_product && line.get_product());
                return product.id;
            });

        let originalTipoDocumento = false;
        let refundedOrderlineIds = [];
        
        if (this.tipo_documento === 'NC') {
            for (const line of orderlines) {
                if (line.refunded_orderline_id) {
                    if (line.refunded_orderline_id.id) {
                        refundedOrderlineIds.push(line.refunded_orderline_id.id);
                    }
                    const originalOrder = line.refunded_orderline_id.order_id;
                    if (originalOrder && originalOrder.get_tipo_documento && originalOrder.get_tipo_documento() && !originalTipoDocumento) {
                        originalTipoDocumento = originalOrder.get_tipo_documento();
                    }
                }
            }
        }

        try {
            const validationResult = await this.orm.call(
                "pos.order",
                "validate_order_for_pos_fe",
                [partnerIdToUse, this.tipo_documento, lineProductIds, this.pos.company.id, originalTipoDocumento, refundedOrderlineIds]
            );

            if (!validationResult.valid) {
                this._showValidationErrorDialog(validationResult.error_message);
                return false;
            }

            const discountCodeValidation = await this._validateDiscountCodes();
            if (!discountCodeValidation) {
                return false;
            }

            return true;

        } catch (error) {
            console.error("❌ Error during FE validation:", error);
            this._showValidationErrorDialog(
                _t("Error al validar los datos del pedido. Por favor intente nuevamente.")
            );
            return false;
        }
    },

    async _validateDiscountCodes() {
        // Odoo 19: use this.currentOrder instead of this.pos.get_order()
        const order = this.currentOrder;
        if (!order) return true;

        if (this.tipo_documento === 'NC') {
            return true;
        }

        const orderlines = getOrderlines(order);
        const linesData = orderlines
            .filter(line => {
                const product = line.product || (line.get_product && line.get_product());
                return product && line.discount > 0;
            })
            .map(line => {
                const product = line.product || (line.get_product && line.get_product());
                const codeId = line.discountCodeId || (line.getDiscountCodeId ? line.getDiscountCodeId() : null);
                return {
                    product_name: product.display_name || product.name || "Unknown",
                    discount: line.discount,
                    discount_code_id: codeId || false,
                };
            });

        if (linesData.length === 0) {
            return true;
        }

        try {
            const validationResult = await this.orm.call(
                "pos.order",
                "validate_discount_codes_for_pos",
                [linesData, this.pos.company.id]
            );

            if (!validationResult.valid) {
                this._showValidationErrorDialog(validationResult.error_message);
                return false;
            }

            return true;
        } catch (error) {
            return true;
        }
    },

    async validateOrder(isForceValidate) {
        const order = this.currentOrder;

        if (this.pos.company.invoice_is_electronic && order) {
            order.to_invoice = true;

            const partner_domain = order.partner_id
                ? [["id", "=", order.partner_id.id]]
                : [["id", "=", this.pos.config.default_partner_id?.id]];
            const checkPartner = await this.orm
                .call("res.partner", "search_read", [], {
                    domain: partner_domain,
                    fields: ["id", "name", "email", "inscribed", "vat"],
                })
                .catch((e) => {
                    console.error("❌ Error consultando partner:", e);
                    return [];
                });

            if (checkPartner.length) {
                const partner = this.pos.models["res.partner"]?.get(checkPartner[0].id) || null;

                // Use helper to set partner on order
                setPartnerOnOrder(order, partner);
                
                // Use safe method call for get_original_total_with_tax
                const totalWithTax = (typeof order.get_original_total_with_tax === 'function') 
                    ? order.get_original_total_with_tax() 
                    : order.get_total_with_tax();
                const isRefund = totalWithTax < 0;
                
                if (isRefund) {
                    this.tipo_documento = "NC";
                } else {
                    this.tipo_documento = checkPartner[0].inscribed ? "FE" : "TE";
                }
                
                // Use the correct method to set tipo documento in Odoo 19
                if (typeof order.set_tipo_documento === 'function') {
                    order.set_tipo_documento(this.tipo_documento);
                }
                
                if (this.tipo_documento === "NC") {
                    let originalInvoiceNumber = "";
                    const orderlines = getOrderlines(order);
                    for (const line of orderlines) {
                        if (line.refunded_orderline_id) {
                            const originalOrder = line.refunded_orderline_id.order_id;
                            if (originalOrder && originalOrder.get_number_electronic && originalOrder.get_number_electronic()) {
                                originalInvoiceNumber = originalOrder.get_number_electronic();
                                break;
                            }
                        }
                    }
                    
                    let refundDetails = null;
                    
                    await new Promise((resolve) => {
                        this.dialog.add(CreditNotePopup, {
                            originalInvoiceNumber: originalInvoiceNumber,
                            getPayload: (payload) => {
                                refundDetails = payload;
                                resolve();
                            },
                            close: () => {
                                resolve();
                            }
                        });
                    });
                    
                    if (refundDetails) {
                        order.set_reason_refund(refundDetails.reason);
                        order.set_refund_reference_code_id(refundDetails.referenceCodeId);
                    } else {
                        return;
                    }
                }
            }

            const isOrderValid = await this._validateOrderForFE();
            if (!isOrderValid) {
                return;
            }

            const [journal] = await this.orm.call("pos.config", "search_read", [], {
                domain: [["id", "=", this.pos.config.id]],
                fields: ["invoice_journal_id"],
                limit: 1,
            });

            const electronic_data = await this.generate_number_electronic(journal.invoice_journal_id[0]);
            
            if (!electronic_data) {
                this._showValidationErrorDialog(
                    _t("Error al generar el número electrónico. Por favor intente nuevamente.")
                );
                return;
            }
            
            order.set_number_electronic(electronic_data.clave);
            order.set_sequence(electronic_data.consecutivo);
        }

        try {
            await super.validateOrder(...arguments);
        } catch (error) {
            console.error("❌ Error during order validation:", error);
            
            if (error.data && error.data.message) {
                this._showValidationErrorDialog(error.data.message);
            } else if (error.message) {
                this._showValidationErrorDialog(error.message);
            }
        }
    },
    
    async generate_number_electronic(journalid) {
        try {
            const journal_data = await this.orm.call("account.journal", "search_read", [], {
                domain: [["id", "=", journalid]],
                fields: ["sucursal", "terminal", "FE_sequence_id", "TE_sequence_id", "NC_sequence_id"]
            });

            let seq_id;
            if (this.tipo_documento === "FE") {
                seq_id = journal_data[0].FE_sequence_id;
            } else if (this.tipo_documento === "TE") {
                seq_id = journal_data[0].TE_sequence_id;
            } else if (this.tipo_documento === "NC") {
                seq_id = journal_data[0].NC_sequence_id;
            }

            if (!seq_id) {
                return null;
            }
            
            const seq_data = await this.orm.call("ir.sequence", "search_read", [], {
                domain: [["id", "=", seq_id[0]]],
                fields: ["number_next_actual", "padding"]
            });

            const idict = {
                year: luxon.DateTime.local().toFormat("yyyy"),
                month: luxon.DateTime.local().toFormat("MM"),
                day: luxon.DateTime.local().toFormat("dd"),
                y: luxon.DateTime.local().toFormat("yy"),
            };

            function pad(n, width, z = "0") {
                n = n + "";
                return n.length < width ? new Array(width - n.length + 1).join(z) + n : n;
            }

            const vat = this.pos.company.vat;
            const num = seq_data[0].number_next_actual;
            
            let tipo_doc = "01";
            if (this.tipo_documento === "TE") {
                tipo_doc = "04";
            } else if (this.tipo_documento === "NC") {
                tipo_doc = "03";
            }

            const consecutivo = pad(journal_data[0].sucursal, 3)
                + pad(journal_data[0].terminal, 5)
                + tipo_doc
                + pad(num, 10);

            const prefix = "506" + idict.day + idict.month + idict.y + pad(vat, 12);
            const situacion = "1";
            const codigo_seguridad = this.generarCodigoSeguridad();
            const clave = prefix + consecutivo + situacion + codigo_seguridad;

            if (clave.length !== 50) {
                throw new Error("La clave generada no tiene 50 dígitos: " + clave);
            }

            return {
                clave: clave,
                consecutivo: consecutivo,
            };

        } catch (error) {
            console.error("Error generating electronic number:", error);
            return null;
        }
    },
    
    generarCodigoSeguridad() {
        return Math.floor(10000000 + Math.random() * 90000000).toString();
    },
});

console.log("✅ PaymentScreen - Exoneration loaded");
