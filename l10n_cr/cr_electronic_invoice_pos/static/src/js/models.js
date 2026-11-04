/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

/**
 * Get partner from order - handles both old and new Odoo 19 API
 */
function getPartnerFromOrder(order) {
    if (!order) return null;
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

/**
 * Get total without tax - handles both old and new Odoo 19 API
 */
function getTotalWithoutTax(order) {
    if (!order) return 0;
    // Direct access to computed totals (Odoo 19)
    if (order.total_without_tax !== undefined) {
        return order.total_without_tax;
    }
    if (typeof order.get_total_without_tax === 'function') {
        return order.get_total_without_tax();
    }
    return 0;
}

function getTotalTax(order) {
    if (!order) return 0;
    // Direct access to computed totals (Odoo 19)
    if (order.total_tax !== undefined) {
        return order.total_tax;
    }
    if (typeof order.get_total_tax === 'function') {
        return order.get_total_tax();
    }
    return 0;
}

/**
 * Calculate exoneration amount
 */
function calculateExonerationAmount(order) {
    const partner = getPartnerFromOrder(order);
    
    if (!hasValidExoneration(partner)) {
        return 0;
    }
    
    const orderlines = getOrderlines(order);
    let totalExoneration = 0;
    const exonerationPercentage = partner.percentage_exoneration || 0;
    
    for (const line of orderlines) {
        const product = line.get_product ? line.get_product() : (line.product || null);
        if (!product) continue;
        
        const basePrice = (line.get_unit_price ? line.get_unit_price() : (line.unit_price || 0)) * 
                         (line.get_quantity ? line.get_quantity() : (line.quantity || 0));
        const discount = line.get_discount ? line.get_discount() : (line.discount || 0);
        const discountedPrice = basePrice * (1 - discount / 100);
        
        totalExoneration += discountedPrice * exonerationPercentage / 100;
    }
    
    return totalExoneration;
}

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        // Store directly on the order object (Odoo 18 compatible)
        this._cr_tipo_documento = vals?.tipo_documento || null;
        this._cr_number_electronic = vals?.number_electronic || null;
        this._cr_sequence = vals?.sequence || null;
        this._cr_journal_id = vals?.journal_id || null;
        this._cr_refund_reason = vals?.refund_reason || null;
        this._cr_refund_reference_code_id = vals?.refund_reference_code_id || null;
    },

    set_tipo_documento(tipoDoc) {
        this._cr_tipo_documento = tipoDoc;
        // Also store directly on order for receipt access
        this.tipo_documento = tipoDoc;
        console.log("✅ tipo_documento set:", tipoDoc);
    },
    get_tipo_documento() {
        return this._cr_tipo_documento || this.tipo_documento || null;
    },

    set_number_electronic(number) {
        this._cr_number_electronic = number;
        // Also store directly on order for receipt access
        this.number_electronic = number;
        console.log("✅ number_electronic set:", number);
    },
    get_number_electronic() {
        return this._cr_number_electronic || this.number_electronic || null;
    },

    set_sequence(number) {
        this._cr_sequence = number;
        // Also store directly on order for receipt access
        this.sequence = number;
    },
    get_sequence() {
        return this._cr_sequence || this.sequence || null;
    },

    set_journal_id(number) {
        this._cr_journal_id = number;
    },
    get_journal_id() {
        return this._cr_journal_id;
    },

    set_reason_refund(reason) {
        this._cr_refund_reason = reason;
    },
    get_reason_refund() {
        return this._cr_refund_reason;
    },
    
    set_refund_reference_code_id(id) {
        this._cr_refund_reference_code_id = id;
    },
    get_refund_reference_code_id() {
        return this._cr_refund_reference_code_id;
    },

    serialize(options) {
        const json = super.serialize(...arguments);
        
        json.tipo_documento = this._cr_tipo_documento;
        json.number_electronic = this._cr_number_electronic;
        json.sequence = this._cr_sequence;
        json.journal_id = this._cr_journal_id;
        json.refund_reason = this._cr_refund_reason;
        json.refund_reference_code_id = this._cr_refund_reference_code_id;
        
        return json;
    },

    export_for_printing() {
        const json = super.export_for_printing(...arguments);
        
        // Add electronic invoice data to headerData
        json.headerData.number_electronic = this._cr_number_electronic;
        json.headerData.tipo_documento = this._cr_tipo_documento;
        
        // Add company address info
        if (this.company_id) {
            json.headerData.company_street = this.company_id.street || '';
            json.headerData.company_county = this.company_id.county_id ? this.company_id.county_id[1] : '';
            json.headerData.company_state = this.company_id.state_id ? this.company_id.state_id[1] : '';
            json.headerData.company_district = this.company_id.district_id ? this.company_id.district_id[1] : '';
            json.headerData.company_country = this.company_id.country_id ? this.company_id.country_id[1] : '';
        }
        
        const partner = getPartnerFromOrder(this) || false;
        json.headerData.partner = partner;
        
        // Add Hacienda required fields
        if (partner) {
            // Partner identification (Nota 4)
            json.headerData.partner_identification_type = partner.identification_type || partner.l10n_cr_identification_type || '01';
            json.headerData.partner_vat = partner.vat || partner.diet_vat || '';
            
            // Sale condition (Nota 5) - default to Contado
            json.headerData.sale_condition = '01'; // Contado
        }
        
        // Economic activity code from company
        if (this.company_id && this.company_id.activity_id) {
            json.headerData.economic_activity_code = this.company_id.activity_id.code || '';
            json.headerData.economic_activity_name = this.company_id.activity_id.name || '';
        }
        
        // Payment method (Hacienda Nota 6)
        const paymentIds = this.payment_ids || [];
        if (paymentIds.length > 0) {
            const paymentMethod = paymentIds[0].payment_method_id || paymentIds[0].payment_method_id;
            if (paymentMethod) {
                const methodName = paymentMethod.name || '';
                let paymentCode = '01'; // Default: Efectivo
                if (methodName.toLowerCase().includes('cash') || methodName.toLowerCase().includes('efectivo')) {
                    paymentCode = '01';
                } else if (methodName.toLowerCase().includes('card') || methodName.toLowerCase().includes('tarjeta')) {
                    paymentCode = '02';
                } else if (methodName.toLowerCase().includes('cheque')) {
                    paymentCode = '03';
                } else if (methodName.toLowerCase().includes('transfer') || methodName.toLowerCase().includes('banco')) {
                    paymentCode = '04';
                } else if (methodName.toLowerCase().includes('sinpe')) {
                    paymentCode = '06';
                } else if (methodName.toLowerCase().includes('digital') || methodName.toLowerCase().includes('plataforma')) {
                    paymentCode = '07';
                } else {
                    paymentCode = '99';
                }
                json.headerData.payment_method_code = paymentCode;
                json.headerData.payment_method_name = methodName;
            }
        }
        
        console.log("📋 export_for_printing:");
        console.log("  number_electronic:", this._cr_number_electronic);
        console.log("  tipo_documento:", this._cr_tipo_documento);
        
        // Initialize exonerationInfo to null (prevent undefined errors)
        json.exonerationInfo = null;
        json.headerData.exonerationInfo = null;
        
        // Add exoneration info for receipt (reuse partner from above)
        if (hasValidExoneration(partner)) {
            const exonerationAmount = calculateExonerationAmount(this);
            
            const originalTax = this.get_original_total_tax ? this.get_original_total_tax() : getTotalTax(this);
            const originalTotal = this.get_original_total_with_tax ? this.get_original_total_with_tax() : (getTotalWithoutTax(this) + originalTax);
            const adjustedTotal = this.get_total_with_tax();
            
            const exonerationInfo = {
                hasExoneration: true,
                percentage: partner.percentage_exoneration || 0,
                type_exoneration: partner.type_exoneration || '',
                number: partner.exoneration_number || '',
                institution: partner.institution_name || '',
                totalExoneration: exonerationAmount,
                fullTaxAmount: originalTax,
                originalTotal: originalTotal,
                netTaxAmount: Math.max(0, originalTax - exonerationAmount),
                adjustedTotal: adjustedTotal,
            };
            
            json.exonerationInfo = exonerationInfo;
            json.headerData.exonerationInfo = exonerationInfo;
            
            console.log("📋 exonerationInfo:", exonerationInfo);
        }
        
        return json;
    },
});

console.log("✅ POS Models - Exoneration loaded");
