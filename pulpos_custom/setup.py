import frappe


def ensure_setup():
	"""Ensure baseline config for FerreTlap: two branches, two warehouses, two price lists."""
	company = "FerreTlap"
	if not frappe.db.exists("Company", company):
		# Nothing to do if the target company isn't created yet.
		frappe.log_error("FerreTlap company not found; skipping pulpos_custom ensure_setup", "pulpos_custom.setup")
		return

	currency = _get_company_currency(company)

	_create_branches(company)
	_create_warehouses(company)
	_create_price_lists(currency)


def _get_company_currency(company: str) -> str:
	company_doc = frappe.get_cached_doc("Company", company)
	# Default to MXN if company/system currency is not set
	return company_doc.default_currency or frappe.db.get_default("currency") or "MXN"


def _create_branches(company: str):
	branches = [
		{"branch": "FerreTlap Matriz", "abbr": "FT-MTZ"},
		{"branch": "FerreTlap Norte", "abbr": "FT-NTE"},
	]

	for b in branches:
		if frappe.db.exists("Branch", b["branch"]):
			continue
		doc = frappe.new_doc("Branch")
		doc.branch = b["branch"]
		doc.company = company
		doc.abbr = b["abbr"]
		doc.insert(ignore_permissions=True)


def _create_warehouses(company: str):
	parent = "All Warehouses"
	warehouses = [
		"FerreTlap Central Warehouse",
		"FerreTlap Norte Warehouse",
	]
	for wh in warehouses:
		if frappe.db.exists("Warehouse", {"warehouse_name": wh, "company": company}):
			continue
		doc = frappe.new_doc("Warehouse")
		doc.warehouse_name = wh
		doc.company = company
		doc.parent_warehouse = parent
		doc.is_group = 0
		doc.insert(ignore_permissions=True)


def _create_price_lists(currency: str):
	price_lists = [
		{"price_list_name": "FerreTlap Retail", "selling": 1, "buying": 0},
		{"price_list_name": "FerreTlap Wholesale", "selling": 1, "buying": 0},
	]
	for pl in price_lists:
		if frappe.db.exists("Price List", pl["price_list_name"]):
			continue
		doc = frappe.new_doc("Price List")
		doc.price_list_name = pl["price_list_name"]
		doc.enabled = 1
		doc.currency = currency
		doc.selling = pl["selling"]
		doc.buying = pl["buying"]
		doc.insert(ignore_permissions=True)
