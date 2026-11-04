/** @odoo-module **/
/**
 * Payment Screen Exoneration Extension for Costa Rica Electronic Invoicing
 * 
 * This module extends PaymentScreen to show exoneration information.
 */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
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
 * Check if a partner has valid exoneration
 * (Duplicated here to avoid import issues)
 */
function _hasValidExoneration(partner) {
    if (!partner) {
        return false;
    }
    
    if (!partner.has_exoneration) {
        return false;
    }
    
    if (partner.date_expiration) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const expirationDate = new Date(partner.date_expiration);
        if (expirationDate < today) {
            return false;
        }
    }
    
    const percentage = partner.percentage_exoneration || 0;
    if (percentage <= 0) {
        return false;
    }
    
    return true;
}

patch(PaymentScreen.prototype, {
    /**
     * Check if current order has active exoneration
     * @returns {Boolean}
     */
    hasActiveExoneration() {
        // Odoo 19: use this.currentOrder instead of this.pos.get_order()
        const order = this.currentOrder;
        if (!order) return false;
        
        const partner = getPartnerFromOrder(order);
        return _hasValidExoneration(partner);
    },

    /**
     * Get exoneration display info for the UI
     * @returns {Object|null}
     */
    getExonerationDisplayInfo() {
        // Odoo 19: use this.currentOrder instead of this.pos.get_order()
        const order = this.currentOrder;
        if (!order) return null;
        
        const partner = getPartnerFromOrder(order);
        if (!_hasValidExoneration(partner)) return null;
        
        const fullTax = order.get_total_tax();
        const exonerationAmount = order.get_total_exoneration ? order.get_total_exoneration() : 0;
        const netTax = Math.max(0, fullTax - exonerationAmount);
        
        let typeName = 'N/A';
        if (partner.type_exoneration) {
            typeName = partner.type_exoneration || 'N/A';
        }
        
        return {
            percentage: partner.percentage_exoneration || 0,
            type: typeName,
            number: partner.exoneration_number || 'N/A',
            fullTax: fullTax,
            exonerationAmount: exonerationAmount,
            netTax: netTax,
            totalSavings: exonerationAmount,
        };
    },

    /**
     * Get formatted exoneration amount
     * @returns {String}
     */
    getFormattedExonerationAmount() {
        const info = this.getExonerationDisplayInfo();
        if (!info) return '₡0.00';
        
        const amount = info.exonerationAmount || 0;
        return `₡${amount.toFixed(2)}`;
    },

    /**
     * Get formatted savings
     * @returns {String}
     */
    getFormattedSavings() {
        const info = this.getExonerationDisplayInfo();
        if (!info) return '₡0.00';
        
        const amount = info.totalSavings || 0;
        return `₡${amount.toFixed(2)}`;
    },
});

console.log("[Exoneración] PaymentScreen extension loaded");
