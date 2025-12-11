(() => {
	// Lightweight client-side UX tweaks and basic inventory validation.

	const getActualQty = async (item_code, warehouse) => {
		if (!item_code || !warehouse) return 0;
		const { message } = await frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Bin",
				filters: { item_code, warehouse },
				fieldname: "actual_qty",
			},
		});
		return (message && message.actual_qty) || 0;
	};

	const warnLowStock = async (frm) => {
		if (!frm.doc.items || !frm.doc.items.length) return;
		let shortfallMessages = [];

		for (const row of frm.doc.items) {
			if (!row.item_code || !row.warehouse || !row.qty) continue;
			const actual = await getActualQty(row.item_code, row.warehouse);
			if (row.qty > actual) {
				shortfallMessages.push(
					`${row.item_code} @ ${row.warehouse}: need ${row.qty}, available ${actual}`
				);
			}
		}

		if (shortfallMessages.length) {
			frappe.throw({
				title: __("Insufficient Stock"),
				message: __("Adjust quantities or warehouse:\n{0}", [shortfallMessages.join("<br>")]),
			});
		}
	};

	frappe.ui.form.on("Item", {
		refresh(frm) {
			if (!frm.is_new()) {
				frm.dashboard.add_comment(
					"info",
					__("Remember to set Default Warehouse and Price List rates for accurate selling.")
				);
			}
		},
	});

	const attachSalesFormUX = (doctype) => {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				frm.dashboard.add_comment(
					"info",
					__("Tip: verify price list and warehouse per line to avoid stock/price issues.")
				);
			},
			async validate(frm) {
				await warnLowStock(frm);
			},
		});
	};

	["Sales Order", "Sales Invoice"].forEach(attachSalesFormUX);
})();
