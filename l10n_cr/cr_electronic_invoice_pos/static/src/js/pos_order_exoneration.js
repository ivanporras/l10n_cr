/** @odoo-module **/
/**
 * POS Order Exoneration Extension for Costa Rica Electronic Invoicing
 * 
 * CRITICAL: This module overrides key total calculation methods to support exoneration.
 * Designed for compatibility with Odoo 19
 */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

/**
 * Get partner from order - handles both old and new Odoo 19 API
 */
function getOrderlines(order) {
    if (typeof order.get_orderlines === 'function') {
        return order.get_orderlines();
    }
    return order.lines || [];
}

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
 * Safe method to call parent method
 */
function callSuperMethod(obj, methodName, args = []) {
    try {
        const proto = Object.getPrototypeOf(Object.getPrototypeOf(obj));
        if (proto && typeof proto[methodName] === 'function') {
            return proto[methodName].apply(obj, args);
        }
    } catch (e) {
        console.warn("Super method call failed:", methodName, e);
    }
    return null;
}

patch(PosOrder.prototype, {
    /**
     * Calculate total exoneration amount for this order
     */
    get_total_exoneration() {
        const partner = getPartnerFromOrder(this);
        
        if (!hasValidExoneration(partner)) {
            return 0;
        }
        
        const orderlines = getOrderlines(this);
        let totalExoneration = 0;
        const exonerationPercentage = partner.percentage_exoneration || 0;
        
        for (const line of orderlines) {
            const product = line.get_product();
            if (!product) continue;
            
            const basePrice = line.get_unit_price() * line.get_quantity();
            const discount = line.get_discount() || 0;
            const discountedPrice = basePrice * (1 - discount / 100);
            
            totalExoneration += discountedPrice * exonerationPercentage / 100;
        }
        
        return totalExoneration;
    },

    /**
     * Get total tax with exoneration applied
     */
    get_total_tax_with_exoneration() {
        const partner = getPartnerFromOrder(this);
        
        if (!hasValidExoneration(partner)) {
            return getTotalTax(this);
        }
        
        return Math.max(0, getTotalTax(this) - this.get_total_exoneration());
    },

    /**
     * Get total with tax after exoneration
     */
    get_total_with_tax_after_exoneration() {
        const partner = getPartnerFromOrder(this);
        
        if (!hasValidExoneration(partner)) {
            const result = callSuperMethod(this, 'get_total_with_tax', [...arguments]);
            if (result !== null) return result;
            return getTotalWithoutTax(this) + getTotalTax(this);
        }
        
        return getTotalWithoutTax(this) + this.get_total_tax_with_exoneration();
    },

    /**
     * Check if current order has exoneration applied
     */
    has_order_exoneration() {
        return hasValidExoneration(getPartnerFromOrder(this));
    },

    /**
     * Get exoneration info for display
     */
    get_exoneration_info() {
        const partner = getPartnerFromOrder(this);
        
        if (!hasValidExoneration(partner)) {
            return null;
        }
        
        return {
            hasExoneration: true,
            percentage: partner.percentage_exoneration || 0,
            type_exoneration: partner.type_exoneration || '',
            number: partner.exoneration_number || '',
            institution: partner.institution_name || '',
            totalExoneration: this.get_total_exoneration(),
            fullTaxAmount: getTotalTax(this),
            netTaxAmount: this.get_total_tax_with_exoneration(),
        };
    },
    
    /**
     * Get total paid from payment_ids
     */
    get_total_paid() {
        let total = 0;
        const payment_ids = this.payment_ids || [];
        
        for (const payment of payment_ids) {
            if (payment.get_amount && typeof payment.get_amount === 'function') {
                total += payment.get_amount();
            } else if (payment.amount !== undefined) {
                total += payment.amount || 0;
            }
        }
        
        return total;
    },
    
    /**
     * Store original total_with_tax for receipt
     */
    get_original_total_with_tax() {
        const result = callSuperMethod(this, 'get_total_with_tax', [...arguments]);
        if (result !== null) return result;
        
        // Fallback: calculate manually
        try {
            return getTotalWithoutTax(this) + getTotalTax(this);
        } catch (e) {
            console.warn("Error calculating original total:", e);
            return 0;
        }
    },
    
    /**
     * Store original total_tax for receipt
     */
    get_original_total_tax() {
        return getTotalTax(this);
    },
    
    /**
     * Override get_total_with_tax - THE KEY METHOD
     * PaymentScreen uses this for all calculations
     */
    get_total_with_tax() {
        const partner = getPartnerFromOrder(this);
        
        if (hasValidExoneration(partner)) {
            return this.get_total_with_tax_after_exoneration();
        }
        
        const result = callSuperMethod(this, 'get_total_with_tax', [...arguments]);
        if (result !== null) return result;
        
        // Fallback
        try {
            return getTotalWithoutTax(this) + getTotalTax(this);
        } catch (e) {
            console.warn("Error in get_total_with_tax:", e);
            return 0;
        }
    },
    
    /**
     * Override get_due - Amount still to be paid
     */
    get_due() {
        try {
            const totalWithTax = this.get_total_with_tax();
            const totalPaid = this.get_total_paid();
            const rounding = this.get_rounding_applied ? this.get_rounding_applied() : 0;
            
            return totalWithTax - totalPaid + rounding;
        } catch (e) {
            console.warn("Error in get_due:", e);
            return 0;
        }
    },
    
    /**
     * Override is_paid - Check if order is fully paid
     */
    is_paid() {
        try {
            const partner = getPartnerFromOrder(this);
            
            if (hasValidExoneration(partner)) {
                return this.get_due() <= 0.00001;
            }
            
            const result = callSuperMethod(this, 'is_paid', [...arguments]);
            if (result !== null) return result;
            
            return this.get_due() <= 0.00001;
        } catch (e) {
            console.warn("Error in is_paid:", e);
            return false;
        }
    },
});

console.log("✅ [Exoneración] PosOrder extension loaded");