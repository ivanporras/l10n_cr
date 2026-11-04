/** @odoo-module **/
/**
 * POS Exoneration Helper Functions for Costa Rica Electronic Invoicing
 * 
 * This module provides helper functions for exoneration calculations.
 * It does NOT patch any classes - just exports utilities.
 */

/**
 * Check if a partner has valid exoneration
 * @param {Object} partner - Partner object
 * @returns {Boolean} True if partner has valid exoneration
 */
export function hasValidExoneration(partner) {
    if (!partner) {
        return false;
    }
    
    // Check if partner has exoneration flag
    if (!partner.has_exoneration) {
        return false;
    }
    
    // Check expiration date
    if (partner.date_expiration) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const expirationDate = new Date(partner.date_expiration);
        if (expirationDate < today) {
            console.log(`[Exoneración] Expirada para cliente ${partner.name}`);
            return false;
        }
    }
    
    // Check percentage
    const percentage = partner.percentage_exoneration || 0;
    if (percentage <= 0) {
        return false;
    }
    
    return true;
}

/**
 * Check if a product CABYS is authorized for exoneration
 * @param {Object} partner - Partner object
 * @param {String} cabysCode - Product CABYS code
 * @param {Object} cabysExonerationData - CABYS exoneration data from server
 * @returns {Boolean} True if CABYS is authorized
 */
export function isCabysAuthorized(partner, cabysCode, cabysExonerationData) {
    if (!partner || !cabysCode) {
        return true; // No CABYS code, allow (will be validated by backend)
    }
    
    const partnerId = partner.id;
    const authorizedCodes = cabysExonerationData?.[partnerId];
    
    // If no specific codes, all CABYS are authorized
    if (!authorizedCodes || authorizedCodes.length === 0) {
        return true;
    }
    
    return authorizedCodes.includes(cabysCode);
}

/**
 * Calculate tax amount with exoneration
 * @param {Number} baseAmount - Base amount (subtotal)
 * @param {Number} taxRate - Tax rate (e.g., 13 for 13%)
 * @param {Number} exonerationPercentage - Exoneration percentage (points of IVA)
 * @returns {Object} Tax calculation result
 */
export function calculateTaxWithExoneration(baseAmount, taxRate, exonerationPercentage) {
    // Calculate full tax amount
    const fullTaxAmount = baseAmount * taxRate / 100;
    
    // Calculate exoneration amount
    const exonerationAmount = baseAmount * exonerationPercentage / 100;
    
    // Net tax = full tax - exoneration
    const netTaxAmount = Math.max(0, fullTaxAmount - exonerationAmount);
    
    return {
        fullTaxAmount: fullTaxAmount,
        exonerationAmount: exonerationAmount,
        netTaxAmount: netTaxAmount,
        exonerationPercentage: exonerationPercentage
    };
}

/**
 * Get CABYS code from a product
 * @param {Object} product - Product object
 * @returns {String|null} CABYS code
 */
export function getProductCabysCode(product) {
    if (!product) return null;
    
    return product.cabys_code || 
           product.cabys_product_id?.codigo || 
           null;
}

console.log("[Exoneración] Helper functions loaded");
