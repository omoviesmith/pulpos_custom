import frappe


def ensure_setup():
	"""Ensure baseline config for FerreTlap: two branches, two warehouses, two price lists."""
	company = "FerreTlap"
	company = _ensure_company(company)

	currency = _get_company_currency(company)

	root_wh = _ensure_root_warehouse(company)

	_create_branches(company)
	_create_warehouses(company, root_wh)
	_create_price_lists(currency)


def _ensure_company(company: str) -> str:
	if frappe.db.exists("Company", company):
		return company

	# If the target company doesn't exist, create it so the rest of the setup can proceed.
	doc = frappe.new_doc("Company")
	doc.company_name = company
	doc.abbr = "FT"
	doc.default_currency = frappe.db.get_default("currency") or "MXN"
	doc.country = frappe.db.get_default("country") or "Mexico"
	doc.insert(ignore_permissions=True)
	return doc.name


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


def _ensure_root_warehouse(company: str) -> str:
	# Try to find existing root for this company
	existing = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ""}, "name"
	)
	if existing:
		return existing

	# Create a root warehouse node if none exists
	root_name = f"All Warehouses - {frappe.get_cached_doc('Company', company).abbr}"
	if frappe.db.exists("Warehouse", root_name):
		return root_name

	doc = frappe.new_doc("Warehouse")
	doc.warehouse_name = root_name
	doc.company = company
	doc.is_group = 1
	doc.parent_warehouse = ""  # root
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_warehouses(company: str, parent: str):
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
