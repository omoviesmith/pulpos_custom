import frappe
from pulpos_custom.website_sync import create_website_items


def ensure_setup():
	"""Ensure baseline config for FerreTlap: two branches, two warehouses, two price lists."""
	company = "FerreTlap"
	company = _ensure_company(company)

	currency = _get_company_currency(company)

	root_wh = _ensure_root_warehouse(company)

	_create_branches(company)
	warehouse_map = _create_warehouses(company, root_wh)
	price_lists = _create_price_lists(currency)
	_ensure_item_prices(price_lists, currency)
	_ensure_mode_of_payment("Cash", company)
	_create_pos_profiles(company, warehouse_map, price_lists)


def ensure_setup_and_publish():
	"""Run baseline setup and publish website items (safe wrapper for after_migrate)."""
	ensure_setup()
	_enable_product_filters()
	_enable_price_and_stock_display()
	_ensure_portal_menu()
	try:
		create_website_items(price_list="FerreTlap Retail", default_warehouse=None, publish=1)
	except Exception as exc:  # pragma: no cover - defensive log to avoid blocking migrations
		frappe.log_error(f"Website Item publish failed: {exc}", "pulpos_custom.ensure_setup_and_publish")


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
	created = {}
	for wh in warehouses:
		if frappe.db.exists("Warehouse", {"warehouse_name": wh, "company": company}):
			created[wh] = frappe.db.get_value(
				"Warehouse", {"warehouse_name": wh, "company": company}
			)
			continue
		doc = frappe.new_doc("Warehouse")
		doc.warehouse_name = wh
		doc.company = company
		doc.parent_warehouse = parent
		doc.is_group = 0
		doc.insert(ignore_permissions=True)
		created[wh] = doc.name
	return created


def _enable_product_filters():
	"""Ensure website product filters (sidebar) are visible by seeding filter config."""
	if not frappe.db.exists("DocType", "E Commerce Settings"):
		return

	try:
		settings = frappe.get_single("E Commerce Settings")
	except Exception:
		return

	changed = False

	# Turn on field filters (e.g. Item Group, Brand) if disabled
	if frappe.db.has_column("E Commerce Settings", "enable_field_filters"):
		if not settings.enable_field_filters:
			settings.enable_field_filters = 1
			changed = True

	def has_filter_field(fieldname: str) -> bool:
		return any(getattr(row, "fieldname", None) == fieldname for row in settings.get("filter_fields", []))

	# Seed common filters if missing and the Website Item doctype supports them
	web_meta = frappe.get_meta("Website Item")
	for fieldname in ("item_group", "brand"):
		if web_meta.has_field(fieldname) and not has_filter_field(fieldname):
			settings.append("filter_fields", {"fieldname": fieldname})
			changed = True

	# Turn on attribute filters and seed a few Item Attributes (e.g., Color, Size) if they exist
	if frappe.db.has_column("E Commerce Settings", "enable_attribute_filters"):
		if not settings.enable_attribute_filters:
			settings.enable_attribute_filters = 1
			changed = True

	def has_attribute_filter(attribute: str) -> bool:
		return any(
			getattr(row, "attribute", None) == attribute for row in settings.get("filter_attributes", [])
		)

	if frappe.db.exists("DocType", "Item Attribute"):
		# Prefer common attributes; fall back to whatever exists
		preferred_attrs = ["Color", "Colour", "Size"]
		existing_attrs = [row.name for row in frappe.get_all("Item Attribute", pluck="name")]
		for attr in preferred_attrs + existing_attrs:
			if attr in existing_attrs and not has_attribute_filter(attr):
				settings.append("filter_attributes", {"attribute": attr})
				changed = True
				# limit seeding to a few to avoid clutter
				if len(settings.get("filter_attributes", [])) >= 3:
					break

	# Make sure linked Item Groups are allowed to show on the website so they appear as filter options
	item_groups = frappe.get_all(
		"Website Item", filters={"published": 1}, pluck="item_group", distinct=True
	)
	for ig in item_groups:
		if ig and frappe.db.exists("Item Group", ig):
			if frappe.db.get_value("Item Group", ig, "show_in_website") != 1:
				frappe.db.set_value("Item Group", ig, "show_in_website", 1)

	if changed:
		settings.save(ignore_permissions=True)


def _enable_price_and_stock_display():
	"""Show price and stock on product cards by toggling settings and backfilling Website Items."""
	if not frappe.db.exists("DocType", "E Commerce Settings"):
		return

	try:
		settings = frappe.get_single("E Commerce Settings")
		web_items_exist = frappe.db.exists("Website Item")
	except Exception:
		return

	changed = False
	for field, desired in {
		"show_price": 1,
		"show_stock_availability": 1,
		"show_actual_qty": 1,
	}.items():
		if getattr(settings, field, None) != desired:
			setattr(settings, field, desired)
			changed = True

	# Align price list to the one we seed (if present)
	if frappe.db.exists("Price List", "FerreTlap Retail") and settings.price_list != "FerreTlap Retail":
		settings.price_list = "FerreTlap Retail"
		changed = True

	if changed:
		settings.save(ignore_permissions=True)

	if not web_items_exist:
		return

	# Backfill Website Items to ensure price/stock flags and a warehouse for stock checks
	# Default to the explicitly requested POS Profile warehouse if present
	pos_default_wh = _get_default_pos_warehouse()
	fallback_wh = pos_default_wh or frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
	web_items = frappe.get_all(
		"Website Item",
		filters={"published": 1},
		fields=["name", "item_code", "website_warehouse", "show_price", "show_stock_availability"],
	)
	for row in web_items:
		updates = {}
		if frappe.db.has_column("Website Item", "show_price") and row.show_price != 1:
			updates["show_price"] = 1
		if frappe.db.has_column("Website Item", "show_stock_availability") and row.show_stock_availability != 1:
			updates["show_stock_availability"] = 1
		# Force website warehouse to the POS warehouse when available to keep stock in sync
		best_wh = pos_default_wh or _pick_warehouse_for_item(
			row.item_code, row.website_warehouse, pos_default_wh, fallback_wh
		)
		if best_wh and best_wh != row.website_warehouse:
			updates["website_warehouse"] = best_wh
		if updates:
			frappe.db.set_value("Website Item", row.name, updates, update_modified=False)


def _pick_warehouse_for_item(
	item_code: str, current_wh: str | None, pos_wh: str | None, fallback: str | None
) -> str | None:
	"""Pick a warehouse that actually has stock, preferring current -> POS -> default -> any stocked -> fallback."""
	if not item_code:
		return current_wh or pos_wh or fallback

	candidates = []
	if current_wh:
		candidates.append(current_wh)
	if pos_wh:
		candidates.append(pos_wh)

	default_wh = frappe.db.get_value("Item", item_code, "default_warehouse")
	if default_wh:
		candidates.append(default_wh)

	# Add any warehouse with stock (highest first)
	stock_wh = frappe.db.sql(
		"""
		select warehouse
		from `tabBin`
		where item_code = %s and actual_qty > 0
		order by actual_qty desc
		limit 1
		""",
		item_code,
	)
	if stock_wh:
		candidates.append(stock_wh[0][0])

	# Finally fallback
	if fallback:
		candidates.append(fallback)

	for wh in candidates:
		if wh and _has_stock(item_code, wh):
			return wh

	# No stock anywhere, keep existing or fallback for consistency
	return current_wh or pos_wh or default_wh or fallback


def _ensure_portal_menu():
	"""Ensure a basic customer portal menu exists (orders, invoices, quotes, issues, communications)."""
	if not frappe.db.exists("DocType", "Portal Settings"):
		return

	try:
		settings = frappe.get_single("Portal Settings")
	except Exception:
		return

	changed = False

	# Turn on portal if field exists
	if frappe.db.has_column("Portal Settings", "enable_portal"):
		if not settings.enable_portal:
			settings.enable_portal = 1
			changed = True

	# Target menu items (title, route)
	menu_items = [
		("Orders", "/orders"),
		("Invoices", "/invoices"),
		("Quotations", "/quotations"),
		("Issues", "/issues"),
		("Communications", "/communications"),
	]

	def has_menu(route: str) -> bool:
		return any(getattr(row, "route", None) == route for row in settings.get("menu_items", []))

	for title, route in menu_items:
		if has_menu(route):
			continue
		item = {
			"title": title,
			"route": route,
			"enabled": 1,
		}
		# Assign Customer role if the child table has role field
		if frappe.db.has_column("Portal Menu Item", "role"):
			item["role"] = "Customer"
		settings.append("menu_items", item)
		changed = True

	if changed:
		settings.save(ignore_permissions=True)


def _get_default_pos_warehouse() -> str | None:
	"""Return the default POS Profile warehouse if configured."""
	# Prefer the configured profile "POS FerreTlap Main" if it exists and has a warehouse
	preferred = frappe.db.get_value("POS Profile", {"name": "POS FerreTlap Main"}, "warehouse")
	if preferred:
		return preferred

	pos_profiles = frappe.get_all(
		"POS Profile",
		fields=["warehouse"],
		filters={"warehouse": ["is", "set"]},
		order_by="modified desc",
		limit_page_length=1,
	)
	return pos_profiles[0].warehouse if pos_profiles else None


def _has_stock(item_code: str, warehouse: str) -> bool:
	"""Check if a Bin has positive qty for item/warehouse."""
	if not item_code or not warehouse:
		return False
	qty = frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
	)
	try:
		return float(qty or 0) > 0
	except Exception:
		return False


def _create_price_lists(currency: str):
	price_lists = [
		{"price_list_name": "FerreTlap Retail", "selling": 1, "buying": 0},
		{"price_list_name": "FerreTlap Wholesale", "selling": 1, "buying": 0},
	]
	names = {}
	for pl in price_lists:
		if frappe.db.exists("Price List", pl["price_list_name"]):
			names[pl["price_list_name"]] = pl["price_list_name"]
			continue
		doc = frappe.new_doc("Price List")
		doc.price_list_name = pl["price_list_name"]
		doc.enabled = 1
		doc.currency = currency
		doc.selling = pl["selling"]
		doc.buying = pl["buying"]
		doc.insert(ignore_permissions=True)
		names[pl["price_list_name"]] = doc.name
	return names


def _ensure_mode_of_payment(name: str, company: str) -> str:
	company_doc = frappe.get_cached_doc("Company", company)
	# Preferred account: company's default cash, else default bank
	account = company_doc.default_cash_account or company_doc.default_bank_account

	if frappe.db.exists("Mode of Payment", name):
		mop = frappe.get_doc("Mode of Payment", name)
		if account and not any(a.company == company for a in mop.accounts):
			mop.append("accounts", {"company": company, "default_account": account})
			mop.save(ignore_permissions=True)
		return name

	doc = frappe.new_doc("Mode of Payment")
	doc.mode_of_payment = name
	doc.type = "Cash"
	doc.enabled = 1
	if account:
		doc.append("accounts", {"company": company, "default_account": account})
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_write_off_account(company: str) -> str | None:
	company_doc = frappe.get_cached_doc("Company", company)
	if company_doc.write_off_account:
		return company_doc.write_off_account
	if company_doc.default_write_off_account:
		return company_doc.default_write_off_account
	# fallback: first non-group Expense account
	return frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Expense Account", "is_group": 0},
		"name",
	)


def _get_cost_center(company: str) -> str | None:
	company_doc = frappe.get_cached_doc("Company", company)
	if company_doc.cost_center:
		return company_doc.cost_center
	if company_doc.default_cost_center:
		return company_doc.default_cost_center
	# fallback: first non-group Cost Center for company
	return frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0}, "name"
	)


def _get_mop_account(mode_of_payment: str, company: str) -> str | None:
	return frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)


def _create_pos_profiles(company: str, warehouses: dict, price_lists: dict):
	"""Create POS Profiles per branch with branch-aware warehouse and price list."""
	profiles = [
		{
			"name": "POS FerreTlap Matriz",
			"branch": "FerreTlap Matriz",
			"warehouse_key": "FerreTlap Central Warehouse",
			"price_list_key": "FerreTlap Retail",
			"default_customer": "Walk-in Customer",
			"default": 1,
		},
		{
			"name": "POS FerreTlap Norte",
			"branch": "FerreTlap Norte",
			"warehouse_key": "FerreTlap Norte Warehouse",
			"price_list_key": "FerreTlap Wholesale",
			"default_customer": "Walk-in Customer",
			"default": 0,
		},
	]

	for pf in profiles:
		if frappe.db.exists("POS Profile", pf["name"]):
			continue

		# Required fields; if missing, skip to avoid migration failure
		mop_account = _get_mop_account("Cash", company)
		write_off_acct = _get_write_off_account(company)
		write_off_cc = _get_cost_center(company)

		if not (mop_account and write_off_acct and write_off_cc):
			frappe.log_error(
				f"Skipping POS Profile {pf['name']} due to missing account/cc. "
				f"MoP account: {mop_account}, Write-off: {write_off_acct}, Cost Center: {write_off_cc}",
				"pulpos_custom.setup",
			)
			continue

		doc = frappe.new_doc("POS Profile")
		doc.name = pf["name"]
		doc.company = company
		doc.branch = pf["branch"]
		doc.warehouse = warehouses.get(pf["warehouse_key"])
		doc.selling_price_list = price_lists.get(pf["price_list_key"])
		doc.is_default = pf["default"]
		doc.allow_print_before_pay = 0
		doc.ignore_pricing_rule = 0
		doc.write_off_account = write_off_acct
		doc.write_off_cost_center = write_off_cc
		if pf.get("default_customer") and frappe.db.exists("Customer", pf["default_customer"]):
			doc.customer = pf["default_customer"]

		# Default payment method (only if Mode of Payment has an account for this company)
		doc.append("payments", {"mode_of_payment": "Cash", "default": 1, "account": mop_account})

		doc.insert(ignore_permissions=True)


def _ensure_item_prices(price_lists: dict, fallback_currency: str):
	"""Backfill Item Price rows for all selling price lists using Item.standard_rate."""
	if not price_lists:
		return

	selling_lists = [pl_name for pl_name in price_lists.values() if pl_name]
	if not selling_lists:
		return

	items = frappe.get_all("Item", fields=["name", "standard_rate", "stock_uom"])
	if not items:
		return

	for pl in selling_lists:
		price_list_currency = (
			frappe.db.get_value("Price List", pl, "currency") if frappe.db.exists("Price List", pl) else None
		) or fallback_currency

		for item in items:
			rate = item.standard_rate or 0
			if float(rate) <= 0:
				continue
			if frappe.db.exists("Item Price", {"item_code": item.name, "price_list": pl}):
				continue

			doc = frappe.new_doc("Item Price")
			doc.item_code = item.name
			doc.price_list = pl
			doc.price_list_rate = rate
			doc.currency = price_list_currency
			doc.selling = 1
			doc.buying = 0
			doc.uom = item.stock_uom
			doc.insert(ignore_permissions=True)
