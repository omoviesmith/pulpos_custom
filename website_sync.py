"""Helper utilities to publish Items as Website Items."""

from __future__ import annotations

import frappe


def create_website_items(
	price_list: str = "FerreTlap Retail",
	default_warehouse: str | None = None,
	publish: int = 1,
) -> dict:
	"""
	Create Website Items for Items that don't already have one.

	- Uses the given selling price list to ensure the Website Item has a price.
	- Falls back to Item.standard_rate if no Item Price is found.
	- Skips Items with no price to avoid publishing zero-priced products.
	- Sets website image from Item.website_image or Item.image.

	Run with:
	bench --site <site> execute "pulpos_custom.website_sync.create_website_items"
	"""
	# Build price map from Item Price for the chosen price list
	price_list_rates = frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "selling": 1},
		fields=["item_code", "price_list_rate"],
	)
	price_map = {row.item_code: float(row.price_list_rate or 0) for row in price_list_rates}

	items = frappe.get_all(
		"Item",
		fields=[
			"name",
			"item_name",
			"item_group",
			"image",
			"website_image",
			"description",
			"default_warehouse",
			"standard_rate",
			"disabled",
		],
	)

	created = []
	skipped = []

	for item in items:
		if item.disabled:
			skipped.append((item.name, "disabled"))
			continue

		if frappe.db.exists("Website Item", {"item_code": item.name}):
			skipped.append((item.name, "exists"))
			continue

		price = price_map.get(item.name) or float(item.standard_rate or 0)
		if price <= 0:
			skipped.append((item.name, "no price"))
			continue

		doc = frappe.new_doc("Website Item")
		doc.item_code = item.name
		doc.item_name = item.item_name
		doc.item_group = item.item_group
		doc.published = publish
		doc.show_price = 1
		doc.show_stock_availability = 1
		doc.website_warehouse = default_warehouse or item.default_warehouse
		doc.website_image = item.website_image or item.image
		doc.thumbnail = item.website_image or item.image
		doc.description = item.description
		doc.save(ignore_permissions=True)
		created.append(item.name)

	return {"created": created, "skipped": skipped}
