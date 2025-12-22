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
	const DEFAULT_CUSTOMER = "Publico General - 1";
	let filterButtonAdded = false;
	let paginationControlsAdded = false;
	const paginationState = {
		currentPage: 1,
		rowsPerPage: Number(localStorage.getItem("pulpos_rows_per_page") || 2) || 2,
		container: null,
		observer: null,
	};
	const ROWS_PER_PAGE_OPTIONS = [1, 2, 3, 4];

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
		addFilterButton();
		initPagination();
		applyPagination();
	};

	const setDefaultCustomer = () => {
		if (customerSet) return;

		// Try cur_pos API first (ERPNext POS object)
		try {
			const fallback =
				(cur_pos?.pos_profile_data && cur_pos.pos_profile_data.customer) ||
				(cur_pos?.frm && cur_pos.frm.doc && cur_pos.frm.doc.customer) ||
				DEFAULT_CUSTOMER ||
				"Walk-in Customer";

			if (window.cur_pos && fallback) {
				const current = cur_pos.customer_field && cur_pos.customer_field.get_value();

				if (cur_pos.set_customer && !current) {
					cur_pos.set_customer(fallback);
					customerSet = true;
					return;
				}

				if (cur_pos.customer_field && !current) {
					cur_pos.customer_field.set_value(fallback);
					customerSet = true;
					return;
				}

				if (cur_pos.frm && cur_pos.frm.set_value && !cur_pos.frm.doc.customer) {
					cur_pos.frm.set_value("customer", fallback);
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
			customerInput.value = DEFAULT_CUSTOMER;
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

	const addFilterButton = () => {
		if (filterButtonAdded) return;
		const filterSection = document.querySelector(".point-of-sale-app .items-selector .filter-section");
		const itemGroupField = document.querySelector(".point-of-sale-app .item-group-field");
		if (!filterSection || !itemGroupField) return;

		// Wrap search and button
		if (!filterSection.classList.contains("pulpos-filter-bar")) {
			filterSection.classList.add("pulpos-filter-bar");
			filterSection.style.position = "relative";
		}

		// Filter button
		const btn = document.createElement("button");
		btn.type = "button";
		btn.className = "pulpos-filter-btn";
		btn.textContent = "Filters";

		// Dropdown menu
		const menu = document.createElement("div");
		menu.className = "pulpos-filter-menu";
		// Move item group field into menu
		menu.appendChild(itemGroupField);
		itemGroupField.style.display = "block";

		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			menu.classList.toggle("show");
		});
		menu.addEventListener("click", (e) => e.stopPropagation());
		document.addEventListener("click", () => {
			menu.classList.remove("show");
		});

		filterSection.appendChild(btn);
		filterSection.appendChild(menu);
		filterButtonAdded = true;
	};

	const getItemsContainer = () =>
		document.querySelector(".point-of-sale-app .pos-items-wrapper") ||
		document.querySelector(".pos .pos-items") ||
		document.querySelector(".pos .items-area") ||
		document.querySelector(".point-of-sale-app .items-area");

	const collectItemCards = (container) =>
		Array.from(
			container.querySelectorAll(
				".item-card, .pos-item-card, .pos-item, .item-wrapper, .item-box, .product-item"
			)
		).filter((el) => el && el.parentElement);

	const calcItemsPerRow = (items) => {
		if (!items.length) return 1;
		const firstTop = items[0].getBoundingClientRect().top;
		const perRow = items.filter(
			(el) => Math.abs(el.getBoundingClientRect().top - firstTop) < 2
		).length;
		return perRow || 1;
	};

	const ensurePaginationControls = () => {
		if (paginationControlsAdded) return;
		const filterSection = document.querySelector(".point-of-sale-app .items-selector .filter-section");
		if (!filterSection) return;

		const wrap = document.createElement("div");
		wrap.className = "pulpos-pagination-controls";

		const label = document.createElement("span");
		label.className = "pulpos-rows-label";
		label.textContent = "Rows per page";

		const select = document.createElement("select");
		select.className = "pulpos-rows-select";
		ROWS_PER_PAGE_OPTIONS.forEach((opt) => {
			const o = document.createElement("option");
			o.value = opt;
			o.textContent = opt;
			if (opt === paginationState.rowsPerPage) o.selected = true;
			select.appendChild(o);
		});
		select.addEventListener("change", () => {
			paginationState.rowsPerPage = Number(select.value) || 1;
			localStorage.setItem("pulpos_rows_per_page", paginationState.rowsPerPage);
			paginationState.currentPage = 1;
			applyPagination();
		});

		const prev = document.createElement("button");
		prev.type = "button";
		prev.className = "pulpos-pagination-btn pulpos-page-prev";
		prev.textContent = "Prev";
		prev.addEventListener("click", () => {
			if (paginationState.currentPage > 1) {
				paginationState.currentPage -= 1;
				applyPagination();
			}
		});

		const pageIndicator = document.createElement("span");
		pageIndicator.className = "pulpos-page-indicator";
		pageIndicator.textContent = "1 / 1";

		const next = document.createElement("button");
		next.type = "button";
		next.className = "pulpos-pagination-btn pulpos-page-next";
		next.textContent = "Next";
		next.addEventListener("click", () => {
			paginationState.currentPage += 1;
			applyPagination();
		});

		wrap.appendChild(label);
		wrap.appendChild(select);
		wrap.appendChild(prev);
		wrap.appendChild(pageIndicator);
		wrap.appendChild(next);
		filterSection.appendChild(wrap);
		paginationControlsAdded = true;
	};

	const updatePaginationControls = (page, totalPages) => {
		const wrap = document.querySelector(".pulpos-pagination-controls");
		if (!wrap) return;
		const indicator = wrap.querySelector(".pulpos-page-indicator");
		if (indicator) indicator.textContent = `${page} / ${totalPages}`;
		const prev = wrap.querySelector(".pulpos-page-prev");
		const next = wrap.querySelector(".pulpos-page-next");
		if (prev) prev.disabled = page <= 1;
		if (next) next.disabled = page >= totalPages;
		const select = wrap.querySelector(".pulpos-rows-select");
		if (select && Number(select.value) !== paginationState.rowsPerPage) {
			select.value = paginationState.rowsPerPage;
		}
	};

	const applyPagination = () => {
		if (!isPosRoute()) return;
		const container = getItemsContainer();
		if (!container) return;

		ensurePaginationControls();
		if (!paginationControlsAdded) return;

		const items = collectItemCards(container);
		if (!items.length) {
			updatePaginationControls(1, 1);
			return;
		}

		const itemsPerRow = calcItemsPerRow(items);
		const rowsPerPage = Math.max(1, paginationState.rowsPerPage);
		const itemsPerPage = Math.max(1, itemsPerRow * rowsPerPage);
		const totalPages = Math.max(1, Math.ceil(items.length / itemsPerPage));

		if (paginationState.currentPage > totalPages) paginationState.currentPage = totalPages;
		if (paginationState.currentPage < 1) paginationState.currentPage = 1;

		const start = (paginationState.currentPage - 1) * itemsPerPage;
		const end = start + itemsPerPage;

		items.forEach((el, idx) => {
			el.style.display = idx >= start && idx < end ? "" : "none";
		});

		updatePaginationControls(paginationState.currentPage, totalPages);
	};

	const initPagination = () => {
		if (!isPosRoute()) return;
		const container = getItemsContainer();
		if (!container) return;
		ensurePaginationControls();
		if (paginationState.container !== container) {
			if (paginationState.observer) paginationState.observer.disconnect();
			paginationState.container = container;
			paginationState.observer = new MutationObserver(() => {
				paginationState.currentPage = 1;
				applyPagination();
			});
			paginationState.observer.observe(container, { childList: true, subtree: true });
		}
	};
})();
