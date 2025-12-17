import frappe


def execute():
	"""Force website items to use the POS warehouse so stock matches POS."""
	pos_wh = frappe.db.get_value("POS Profile", {"name": "POS FerreTlap Main"}, "warehouse")
	if not pos_wh:
		pos_profiles = frappe.get_all(
			"POS Profile",
			fields=["warehouse"],
			filters={"warehouse": ["is", "set"]},
			order_by="modified desc",
			limit_page_length=1,
		)
		pos_wh = pos_profiles[0].warehouse if pos_profiles else None

	# Fallbacks if POS Profile warehouse is missing
	fallback_wh = (
		frappe.db.get_value(
			"Warehouse", {"warehouse_name": "FerreTlap Central Warehouse", "is_group": 0}, "name"
		)
		or frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
	)

	target_wh = pos_wh or fallback_wh
	if not target_wh:
		return

	web_items = frappe.get_all(
		"Website Item",
		filters={"published": 1},
		fields=["name", "item_code", "website_warehouse"],
	)

	for row in web_items:
		# If already set to target, skip
		if row.website_warehouse == target_wh:
			continue

		# If the existing website warehouse has stock, keep it; else use target
		if row.website_warehouse and _has_stock(row.item_code, row.website_warehouse):
			continue

		payload = {"website_warehouse": target_wh}
		if frappe.db.has_column("Website Item", "show_stock_availability"):
			payload["show_stock_availability"] = 1
		if frappe.db.has_column("Website Item", "show_price"):
			payload["show_price"] = 1

		frappe.db.set_value("Website Item", row.name, payload, update_modified=False)


def _has_stock(item_code: str, warehouse: str) -> bool:
	if not item_code or not warehouse:
		return False
	qty = frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
	)
	try:
		return float(qty or 0) > 0
	except Exception:
		return False
