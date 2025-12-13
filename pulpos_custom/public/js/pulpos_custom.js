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

	// POS enhancements: dark/yellow skin, quick search focus, quick-pay buttons (non-invasive)
	const POS_ROUTES = ["point-of-sale", "pos"];
	let quickPayInjected = false;
	let posClassApplied = false;
	let customerSet = false;

	const isPosRoute = () => {
		const r = frappe.get_route && frappe.get_route();
		if (r && r.length && POS_ROUTES.includes(r[0])) return true;
		// Fallback for direct URL load
		return window.location.pathname.includes("point-of-sale") || window.location.pathname.endsWith("/pos");
	};

	const focusPosSearch = () => {
		const search = document.querySelector(
			'.pos input[type="text"][placeholder*="Search"], .pos .search-bar input, input[placeholder*="Search Item"]'
		);
		if (search) search.focus();
	};

	const injectQuickPay = () => {
		if (quickPayInjected) return;
		const payArea =
			document.querySelector(".pos .pay-section") ||
			document.querySelector(".pos .cart-footer") ||
			document.querySelector(".modal .modal-footer");
		if (!payArea) return;

		const container = document.createElement("div");
		container.className = "pulpos-quick-pay";

		[50, 100, 200].forEach((amt) => {
			const btn = document.createElement("button");
			btn.type = "button";
			btn.textContent = `${frappe.sys_defaults && frappe.sys_defaults.currency ? frappe.sys_defaults.currency : "$"}${amt}`;
			btn.addEventListener("click", () => {
				const payInput =
					document.querySelector('.pos input[name="paid_amount"]') ||
					document.querySelector('.modal input[name="paid_amount"]') ||
					document.querySelector('.pos input[placeholder*="Amount"]');
				if (payInput) {
					payInput.value = amt;
					payInput.dispatchEvent(new Event("input", { bubbles: true }));
				}
			});
			container.appendChild(btn);
		});

		payArea.prepend(container);
		quickPayInjected = true;
	};

	const applyPosEnhancements = () => {
		if (!isPosRoute()) return;
		if (!posClassApplied) {
			document.body.classList.add("pulpos-pos");
			posClassApplied = true;
		}
		focusPosSearch();
		injectQuickPay();
		setDefaultCustomer();
	};

	const setDefaultCustomer = () => {
		if (customerSet) return;

		// Try cur_pos API first (ERPNext POS object)
		try {
			if (window.cur_pos && cur_pos.customer_field) {
				const current = cur_pos.customer_field.get_value();
				const fallback = (cur_pos.pos_profile_data && cur_pos.pos_profile_data.customer) || "Publico General - 1";
				if (!current && fallback) {
					cur_pos.customer_field.set_value(fallback);
					customerSet = true;
					return;
				}
				if (current) {
					customerSet = true;
					return;
				}
			}
		} catch (e) {
			// ignore
		}

		// Fallback: set the DOM input if empty
		const customerInput = document.querySelector(
			'.customer-section input[data-fieldtype="Link"], .customer-section input[placeholder*="Cliente"]'
		);
		if (customerInput && !customerInput.value) {
			customerInput.value = "Publico General - 1";
			customerInput.dispatchEvent(new Event("input", { bubbles: true }));
			customerInput.dispatchEvent(new Event("change", { bubbles: true }));
			customerSet = true;
		}
	};

	// React to route changes and initial load
	frappe.router && frappe.router.on("change", () => {
		quickPayInjected = false;
		posClassApplied = false;
		setTimeout(applyPosEnhancements, 100);
		setTimeout(applyPosEnhancements, 500);
	});
	setTimeout(applyPosEnhancements, 200);
	setTimeout(applyPosEnhancements, 1200);
	// Keep trying for SPA hiccups
	setInterval(() => {
		if (isPosRoute()) applyPosEnhancements();
	}, 3000);
})();
