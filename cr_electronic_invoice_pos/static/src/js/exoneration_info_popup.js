/** @odoo-module **/
/**
 * Exoneration Info Popup for Costa Rica Electronic Invoicing
 * 
 * This popup displays exoneration details for the current order.
 */

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class ExonerationInfoPopup extends Component {
    static template = "cr_electronic_invoice_pos.ExonerationInfoPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        exonerationInfo: { type: Object, optional: true },
    };

    setup() {
        this.pos = useService("pos");
    }

    get title() {
        return _t("Detalles de Exoneración");
    }

    get percentage() {
        return this.props.exonerationInfo?.percentage || 0;
    }

    get documentType() {
        return this.props.exonerationInfo?.type || 'N/A';
    }

    get documentNumber() {
        return this.props.exonerationInfo?.number || 'N/A';
    }

    get fullTax() {
        const amount = this.props.exonerationInfo?.fullTax || 0;
        return this.formatCurrency(amount);
    }

    get exonerationAmount() {
        const amount = this.props.exonerationInfo?.exonerationAmount || 0;
        return this.formatCurrency(amount);
    }

    get netTax() {
        const amount = this.props.exonerationInfo?.netTax || 0;
        return this.formatCurrency(amount);
    }

    get totalSavings() {
        const amount = this.props.exonerationInfo?.totalSavings || 0;
        return this.formatCurrency(amount);
    }

    formatCurrency(amount) {
        return `₡${amount.toFixed(2)}`;
    }

    confirm() {
        this.props.close();
    }
}

console.log("[Exoneración] ExonerationInfoPopup loaded");
