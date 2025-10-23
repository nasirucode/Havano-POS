import frappe
from frappe import _
from havano_pos_integration.utils import create_response
from frappe.utils import now_datetime

@frappe.whitelist()
def test_api(name):
    # Create a welcome message
    try:
        msg = f"Welcome {name}!!!"
        # Fetch product details
        product_details = frappe.get_all("Item", fields=["name", "item_code", "item_group"])
        create_response("200", msg, product_details)
        return
    except Exception:
        create_response("417","Error in getting product details")
        return

@frappe.whitelist()
def create_pos_opening_entry():
    try:
        # Get form data
        data = frappe.local.form_dict

        # Check for required fields
        required_fields = ["period_start_date", "company", "user", "pos_profile", "balance_details"]
        for field in required_fields:
            if field not in data:
                frappe.throw(_("Missing required field: {0}").format(field))

        # Create POS Opening Entry document
        pos_opening_entry = frappe.get_doc({
            "doctype": "POS Opening Entry",
            "period_start_date": data.get("period_start_date"),
            "company": data.get("company"),
            "user": data.get("user"),
            "pos_profile": data.get("pos_profile"),
            "balance_details": data.get("balance_details")
        })

        # Insert and submit the document
        pos_opening_entry.insert()
        pos_opening_entry.submit()

        # Commit the transaction
        frappe.db.commit()
        create_response("200", pos_opening_entry.as_dict())
        return
    except Exception as e:
        # Log error and return error message
        create_response("417",{"error": str(e)})
        frappe.log_error(message=str(e), title="Error creating POS Opening Entry")
        return

@frappe.whitelist()
def get_inventory():
    # Fetch price list, inventory, and item price list
    try:
        price_list = frappe.get_all("Price List", fields = ["price_list_name","currency"])
        inventory = frappe.get_all("Bin", fields = ["item_code","valuation_rate","warehouse","actual_qty","ordered_qty","stock_value"])
        item_price_list = frappe.get_all("Item Price", fields = ["item_code","uom","price_list","price_list_rate","currency","currency","supplier"])
        create_response("200", { "price_list": price_list, "inventory": inventory, "item_price_list": item_price_list })
        return 
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching inventory data")
        return

@frappe.whitelist()
def get_warehouses():
    try:
        # Fetch inventory and warehouse details
        inventory = frappe.get_all("Bin", fields=["item_code", "valuation_rate", "warehouse", "actual_qty", "ordered_qty", "stock_value"])
        warehouses = frappe.get_all("Warehouse", fields=["name", "company", "account", "warehouse_type"])
        
        # Calculate total quantity and value for each warehouse
        warehouse_inventory = {}
        for item in inventory:
            warehouse = item["warehouse"]
            if warehouse not in warehouse_inventory:
                warehouse_inventory[warehouse] = {
                    "total_quantity": 0,
                    "total_value": 0
                }
            warehouse_inventory[warehouse]["total_quantity"] += item["actual_qty"]
            warehouse_inventory[warehouse]["total_value"] += item["stock_value"]

        # Add total quantity and value to warehouse details
        for warehouse in warehouses:
            name = warehouse["name"]
            warehouse["total_quantity"] = warehouse_inventory.get(name, {}).get("total_quantity", 0)
            warehouse["total_value"] = warehouse_inventory.get(name, {}).get("total_value", 0)
        create_response("200", warehouses)
        return
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching warehouse data")
        return

@frappe.whitelist()
def get_cost_center():
    try:
        # Fetch cost center details
        cost_center = frappe.get_all("Cost Center", fields = ["name","cost_center_name", "cost_center_number", "parent_cost_center", "company"])
        create_response("200", cost_center)
        return
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching cost center data")
        return

@frappe.whitelist()
def get_pos_profile():
    # Fetch POS profile details
    pos_profiles = frappe.get_all("POS Profile", fields=["name", "company", "warehouse", "customer", "company_address", "cost_center","selling_price_list"])

    response = []

    for profile in pos_profiles:
        profile_data = {
            "name": profile.name,
            "company": profile.company,
            "warehouse": profile.warehouse,
            "customer": profile.customer,
            "company_address": profile.company_address,
            "cost_center": profile.cost_center,
            "applicable_for_users": [],
            "payments": [],
            "price_list": profile.selling_price_list
        }

        # Fetch applicable users for the profile
        try: 
            if frappe.db.exists("POS Profile User",{"parent":profile.name}):
                applicable_for_users = frappe.get_all("POS Profile User",filters={"parent": profile.name}, fields=["user","default"])
                profile_data["applicable_for_users"] = applicable_for_users if applicable_for_users else []
            else:
                profile_data["applicable_for_users"] = []
        except Exception as e: 
            profile_data["applicable_for_users"] = []
        
        # Fetch payment methods for the profile
        try: 
            if frappe.db.exists("POS Payment Method",{"parent":profile.name}):
               payments = frappe.get_all("POS Payment Method", filters={"parent": profile.name}, fields=["mode_of_payment", "default"])
               profile_data["payments"] = payments if payments else []
            else:
                profile_data["payments"] = []
        except Exception as e:
            profile_data["payments"] = []

        response.append(profile_data)

    return response


@frappe.whitelist()
def get_products():
    try:
        # Get form data
        data = frappe.local.form_dict
        
        # Get pagination parameters
        page = int(data.get("page", 1))
        limit = int(data.get("limit", 1000))
        
        # Validate pagination parameters
        if page < 1:
            page = 1
        # if limit < 1 or limit > 100:  # Max limit of 100 to prevent performance issues
        #     limit = 20
            
        # Calculate start for pagination
        start = (page - 1) * limit
        
        # Get item_group from request body, if provided (can be single string or list)
        item_group = data.get("item_group")
        
        # Get user's allowed item groups from permissions
        user_item_groups = frappe.get_all(
            "User Permission",
            filters={"user": frappe.session.user, "allow": "Item Group"},
            fields=["for_value"]
        )
        user_item_group_list = [ig["for_value"] for ig in user_item_groups]
        
        # Build filters based on whether item_group is provided
        filters = {}
        
        filters['disabled'] = 0
        
        # Handle item_group filtering (supports both single string and list)
        if item_group:
            # Convert single item_group to list for consistent handling
            if isinstance(item_group, str):
                requested_groups = [item_group]
            elif isinstance(item_group, list):
                requested_groups = item_group
            else:
                requested_groups = []
            
            # Filter requested groups to only include those user has permission for
            if user_item_group_list:
                # User has specific permissions, filter requested groups
                allowed_groups = [group for group in requested_groups if group in user_item_group_list]
                if allowed_groups:
                    if len(allowed_groups) == 1:
                        filters['item_group'] = allowed_groups[0]
                    else:
                        filters['item_group'] = ["in", allowed_groups]
                else:
                    # No requested groups are allowed, use user's allowed groups
                    filters['item_group'] = ["in", user_item_group_list]
            else:
                # User has no specific permissions, use all requested groups
                if len(requested_groups) == 1:
                    filters['item_group'] = requested_groups[0]
                else:
                    filters['item_group'] = ["in", requested_groups]
        else:
            # No specific item_group requested, use user's allowed groups
            if user_item_group_list:
                filters['item_group'] = ["in", user_item_group_list]
        # if user_cost_center:
        #     filters['cost_center'] = ["=", user_cost_center]
        
        # Get total count for pagination metadata
        total_count = frappe.db.count("Item", filters=filters)
        
        # Fetch paginated product details
        product_details = frappe.get_all("Item", 
            filters=filters,
            fields=["name","item_name", "item_code", "item_group", "is_stock_item"],
            start=start,
            limit=limit,
            order_by="item_code"
        )
        
        products_data = frappe.get_all("Bin", fields=["item_code", "warehouse", "actual_qty"])
        price_lists = frappe.get_all("Item Price", fields=["price_list", "price_list_rate", "item_code","selling","buying"])
        
        # Initialize products dictionary with all items
        products = {detail['item_code']: {"warehouses": [], "prices": [], "taxes": []} for detail in product_details}
        
        # Add warehouse data
        for product in products_data:
            item_code = product["item_code"]
            if item_code in products:
                products[item_code]["warehouses"].append({
                    "warehouse": product["warehouse"],
                    "qtyOnHand": product["actual_qty"]
                })

        for item_code, pdata in products.items():
            if not pdata["warehouses"]:
                pdata["warehouses"].append({
                    "warehouse": None,
                    "qtyOnHand": 0
                })
        
        # Add price list data
        for price in price_lists:
            item_code = price["item_code"]
            if item_code in products:
                products[item_code]["prices"].append({
                    "priceName": price["price_list"],
                    "price": price["price_list_rate"],
                    "type": "selling" if price["selling"] else "buying"
                })
        
        # Fetch taxes for each item individually
        for detail in product_details:
            item_code = detail["item_code"]
            try:
                # Get the full Item document to access child table
                item_doc = frappe.get_doc("Item", item_code)
                
                # Access the taxes child table
                if hasattr(item_doc, 'taxes') and item_doc.taxes:
                    for tax_row in item_doc.taxes:
                        tax_info = {
                            "item_tax_template": getattr(tax_row, 'item_tax_template', ''),
                            "tax_category": getattr(tax_row, 'tax_category', ''),
                            "valid_from": getattr(tax_row, 'valid_from', ''),
                            "minimum_net_rate": getattr(tax_row, 'minimum_net_rate', 0),
                            "maximum_net_rate": getattr(tax_row, 'maximum_net_rate', 0)
                        }
                        products[item_code]["taxes"].append(tax_info)
            except Exception as tax_error:
                # If there's an error fetching taxes for this item, continue with empty taxes
                frappe.log_error(message=f"Error fetching taxes for item {item_code}: {str(tax_error)}", 
                               title="Item Tax Fetch Error")
                continue
        
        # Compile final products list
        final_products = []
        for detail in product_details:
            item_code = detail["item_code"]
            final_product = {
                "itemcode": item_code,
                "itemname": detail["item_name"],
                "groupname": detail["item_group"],
                "maintainstock": detail["is_stock_item"],
                "warehouses": products[item_code]["warehouses"],
                "prices": products[item_code]["prices"],
                "taxes": products[item_code]["taxes"]
            }
            final_products.append(final_product)
        
        # Calculate pagination metadata
        total_pages = (total_count + limit - 1) // limit  # Ceiling division
        has_next_page = page < total_pages
        has_prev_page = page > 1
        
        # Create pagination response
        pagination_response = {
            "products": final_products,
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next_page": has_next_page,
                "has_prev_page": has_prev_page,
                "next_page": page + 1 if has_next_page else None,
                "prev_page": page - 1 if has_prev_page else None
            }
        }
        
        create_response("200", pagination_response)
        return
        
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching products data")
        return


@frappe.whitelist()
def get_sales_invoice(user=None):
    try:
        final_invoice = []
        # Return all invoices if user is Administrator, else filter by user
        filters = {} if user == "Administrator" else {"owner": user} if user else {}
        
        sales_invoice_list = frappe.get_all("Sales Invoice", 
            filters=filters,
            fields=[
                "name", "customer", "company", "customer_name",
                "posting_date", "posting_time", "due_date",
                "total_qty", "total", "total_taxes_and_charges",
                "grand_total", "owner", "modified_by"
            ])
        
        for invoice in sales_invoice_list:
            items = frappe.get_all("Sales Invoice Item", 
                filters={"parent": invoice.name},
                fields=["item_name", "qty", "rate", "amount"])
                
            invoice = {
                "name": invoice.name,
                "customer": invoice.customer,
                "company": invoice.company,
                "customer_name": invoice.customer_name,
                "posting_date": invoice.posting_date,
                "posting_time": invoice.posting_time,
                "due_date": invoice.due_date,
                "items": items,
                "total_qty": invoice.total_qty,
                "total": invoice.total,
                "total_taxes_and_charges": invoice.total_taxes_and_charges,
                "grand_total": invoice.grand_total,
                "created_by": invoice.owner,
                "last_modified_by": invoice.modified_by
            }
            final_invoice.append(invoice)
            
        create_response("200", final_invoice)
        return
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching sales invoice data")
        return

@frappe.whitelist()
def get_user():
    try:
        users = frappe.get_all("User", 
            fields=["email", "first_name", "last_name", "username", "gender", "location"])
        
        for user in users:
            sales_invoices = frappe.get_all("Sales Invoice",
                filters={"owner": user.email},
                fields=[
                    "name", 
                    "posting_date",
                    "posting_time", 
                    "due_date",
                    "customer",
                    "customer_name",
                    "company",
                    "total_qty",
                    "total",
                    "total_taxes_and_charges", 
                    "grand_total",
                    "status"
                ]
            )
            
            for invoice in sales_invoices:
                # Get items for each invoice
                invoice.items = frappe.get_all("Sales Invoice Item",
                    filters={"parent": invoice.name},
                    fields=["item_name", "qty", "rate", "amount"]
                )
            
            user["sales_invoices"] = sales_invoices
            user["total_sales"] = sum(invoice.grand_total for invoice in sales_invoices)
            user["total_invoices"] = len(sales_invoices)
            
        create_response("200", users)
        return
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching user data")
        return

@frappe.whitelist()
def get_customer():
    try:
        # Get form data
        data = frappe.local.form_dict
        
        # Get pagination parameters
        page = int(data.get("page", 1))
        limit = int(data.get("limit", 1000))
        
        # Validate pagination parameters
        if page < 1:
            page = 1
            
        # Calculate start for pagination
        start = (page - 1) * limit
        
        # default_cost_center = frappe.db.get_value("User Permission", {"user": frappe.session.user, "allow": "Cost Center", "is_default": 1}, "for_value")       
        
        # # Build filters
        filters = {}
        # filters = {"custom_cost_center": default_cost_center, "default_price_list": ["!=", ""]}
        
        # Get total count for pagination metadata
        total_count = frappe.db.count("Customer", filters=filters)
        
        # Fetch customer details with default price list (with pagination)
        customers = frappe.get_all("Customer", 
            filters=filters,
            fields=["name", "customer_name","customer_type","custom_cost_center","custom_warehouse","gender","customer_pos_id","default_price_list", "customer_group"],
            start=start,
            limit=limit,
            order_by="name"
        )
        
        for customer in customers:
            # Fetch item prices for each customer
            customer.items = frappe.get_all("Item Price", filters = {"price_list":customer.default_price_list}, fields = ["item_code","item_name","price_list_rate"])
            
            # Get customer balance (receivables)
            try:
                # Method 1: Using frappe.db.sql to get outstanding amount from GL Entry
                customer_balance = frappe.db.sql("""
                    SELECT IFNULL(SUM(debit - credit), 0) as balance
                    FROM `tabGL Entry`
                    WHERE party_type = 'Customer' 
                    AND party = %s 
                    AND is_cancelled = 0
                """, (customer.name,))[0][0] or 0
                
                customer.balance = customer_balance
                
                # Alternative Method 2: Get outstanding amount from Sales Invoice
                outstanding_invoices = frappe.db.sql("""
                    SELECT IFNULL(SUM(outstanding_amount), 0) as outstanding
                    FROM `tabSales Invoice`
                    WHERE customer = %s 
                    AND docstatus = 1
                    AND outstanding_amount > 0
                """, (customer.name,))[0][0] or 0
                
                customer.outstanding_amount = outstanding_invoices
                
                # # Method 3: Using ERPNext's get_balance_on function for more accuracy
                # from erpnext.accounts.utils import get_balance_on
                # from frappe.utils import today
                
                # # Get the receivable account for this customer
                # receivable_account = frappe.db.get_value("Customer", customer.name, "accounts")
                # if not receivable_account:
                #     # Get default receivable account from company
                #     company = frappe.db.get_value("Customer", customer.name, "default_company") or frappe.defaults.get_user_default("Company")
                #     receivable_account = frappe.db.get_value("Company", company, "default_receivable_account")
                
                # if receivable_account:
                #     account_balance = get_balance_on(
                #         account=receivable_account,
                #         # date=today(),
                #         party_type="Customer",
                #         party=customer.name
                #     )
                #     customer.account_balance = account_balance
                # else:
                #     customer.account_balance = 0
                    
            except Exception as balance_error:
                frappe.log_error(message=f"Error fetching balance for customer {customer.name}: {str(balance_error)}", 
                               title="Customer Balance Fetch Error")
                customer.balance = 0
                customer.outstanding_amount = 0
                # customer.account_balance = 0
            
            # Get customer loyalty points
            try:
                # Method 1: Get current loyalty points from Loyalty Point Entry
                loyalty_points = frappe.db.sql("""
                    SELECT IFNULL(SUM(loyalty_points), 0) as total_points
                    FROM `tabLoyalty Point Entry`
                    WHERE customer = %s 
                    AND docstatus = 1
                    AND expiry_date >= CURDATE()
                """, (customer.name,))[0][0] or 0
                
                customer.loyalty_points = loyalty_points
                
                # Method 2: Get loyalty points details with expiry dates
                loyalty_point_details = frappe.db.sql("""
                    SELECT 
                        loyalty_points,
                        expiry_date,
                        loyalty_program,
                        invoice_type,
                        invoice,
                        posting_date
                    FROM `tabLoyalty Point Entry`
                    WHERE customer = %s 
                    AND docstatus = 1
                    AND expiry_date >= CURDATE()
                    ORDER BY expiry_date ASC
                """, (customer.name,), as_dict=True)
                
                customer.loyalty_point_details = loyalty_point_details
                
                # Method 3: Get loyalty program information for the customer
                loyalty_program_info = frappe.db.sql("""
                    SELECT DISTINCT
                        lpe.loyalty_program,
                        lp.loyalty_program_name,
                        lp.loyalty_program_type,
                        lp.conversion_factor
                    FROM `tabLoyalty Point Entry` lpe
                    LEFT JOIN `tabLoyalty Program` lp ON lpe.loyalty_program = lp.name
                    WHERE lpe.customer = %s 
                    AND lpe.docstatus = 1
                """, (customer.name,), as_dict=True)
                
                customer.loyalty_programs = loyalty_program_info
                
                # Method 4: Get redeemed loyalty points
                redeemed_points = frappe.db.sql("""
                    SELECT IFNULL(SUM(ABS(loyalty_points)), 0) as redeemed_points
                    FROM `tabLoyalty Point Entry`
                    WHERE customer = %s 
                    AND docstatus = 1
                    AND loyalty_points < 0
                """, (customer.name,))[0][0] or 0
                
                customer.redeemed_loyalty_points = redeemed_points
                
                # Calculate net available loyalty points
                earned_points = frappe.db.sql("""
                    SELECT IFNULL(SUM(loyalty_points), 0) as earned_points
                    FROM `tabLoyalty Point Entry`
                    WHERE customer = %s 
                    AND docstatus = 1
                    AND loyalty_points > 0
                    AND expiry_date >= CURDATE()
                """, (customer.name,))[0][0] or 0
                
                customer.earned_loyalty_points = earned_points
                customer.net_loyalty_points = earned_points - redeemed_points
                
            except Exception as loyalty_error:
                frappe.log_error(message=f"Error fetching loyalty points for customer {customer.name}: {str(loyalty_error)}", 
                               title="Customer Loyalty Points Fetch Error")
                customer.loyalty_points = 0
                customer.loyalty_point_details = []
                customer.loyalty_programs = []
                customer.redeemed_loyalty_points = 0
                customer.earned_loyalty_points = 0
                customer.net_loyalty_points = 0
        
        # Calculate pagination metadata
        total_pages = (total_count + limit - 1) // limit  # Ceiling division
        has_next_page = page < total_pages
        has_prev_page = page > 1
        
        # Create pagination response
        pagination_response = {
            "customers": customers,
            "pagination": {
                "current_page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next_page": has_next_page,
                "has_prev_page": has_prev_page,
                "next_page": page + 1 if has_next_page else None,
                "prev_page": page - 1 if has_prev_page else None
            }
        }
        
        create_response("200", pagination_response)
        return
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching customer data")
        return

@frappe.whitelist()
def redeem_loyalty_points():
    try:
        # Get form data
        data = frappe.local.form_dict
        
        # Check for required fields
        required_fields = ["customer", "loyalty_points", "company"]
        for field in required_fields:
            if field not in data:
                create_response("417", {"error": f"Missing required field: {field}"})
                return

        customer = data.get("customer")
        points_to_redeem = float(data.get("loyalty_points", 0))
        company = data.get("company")
        loyalty_program = data.get("loyalty_program")  # Optional
        sales_invoice = data.get("sales_invoice")  # Optional - if redeeming against specific invoice
        
        # Validate points to redeem
        if points_to_redeem <= 0:
            create_response("417", {"error": "Points to redeem must be greater than 0"})
            return
        
        # Check if customer exists
        if not frappe.db.exists("Customer", customer):
            create_response("417", {"error": f"Customer {customer} does not exist"})
            return
        
        # Get available loyalty points for the customer
        available_points = frappe.db.sql("""
            SELECT IFNULL(SUM(loyalty_points), 0) as available_points
            FROM `tabLoyalty Point Entry`
            WHERE customer = %s 
            AND docstatus = 1
            AND expiry_date >= CURDATE()
            AND loyalty_points > 0
        """, (customer,))[0][0] or 0
        
        # Check if customer has enough points
        if points_to_redeem > available_points:
            create_response("417", {
                "error": f"Insufficient loyalty points. Available: {available_points}, Requested: {points_to_redeem}"
            })
            return
        
        # Get loyalty program if not provided
        if not loyalty_program:
            loyalty_program_data = frappe.db.sql("""
                SELECT DISTINCT loyalty_program
                FROM `tabLoyalty Point Entry`
                WHERE customer = %s 
                AND docstatus = 1
                AND loyalty_points > 0
                LIMIT 1
            """, (customer,))
            
            if loyalty_program_data:
                loyalty_program = loyalty_program_data[0][0]
            else:
                create_response("417", {"error": "No loyalty program found for customer"})
                return
        
        # Get loyalty program details for conversion factor
        loyalty_program_doc = frappe.get_doc("Loyalty Program", loyalty_program)
        conversion_factor = loyalty_program_doc.conversion_factor or 1
        
        # Calculate redemption amount
        redemption_amount = points_to_redeem * conversion_factor
        
        # Create Loyalty Point Entry for redemption (negative points)
        loyalty_point_entry = frappe.get_doc({
            "doctype": "Loyalty Point Entry",
            "customer": customer,
            "loyalty_program": loyalty_program,
            "loyalty_points": -points_to_redeem,  # Negative for redemption
            "posting_date": data.get("posting_date", frappe.utils.today()),
            "company": company,
            "expiry_date": frappe.utils.add_years(frappe.utils.today(), 10),  # Far future date for redeemed points
            "invoice_type": "Sales Invoice" if sales_invoice else "",
            "invoice": sales_invoice or "",
            "redemption_amount": redemption_amount
        })
        
        # Insert and submit the loyalty point entry
        loyalty_point_entry.insert()
        loyalty_point_entry.submit()
        
        # Commit the transaction
        frappe.db.commit()
        
        # Get updated loyalty points balance
        updated_balance = frappe.db.sql("""
            SELECT IFNULL(SUM(loyalty_points), 0) as balance
            FROM `tabLoyalty Point Entry`
            WHERE customer = %s 
            AND docstatus = 1
            AND expiry_date >= CURDATE()
        """, (customer,))[0][0] or 0
        
        response_data = {
            "message": "Loyalty points redeemed successfully",
            "redemption_details": {
                "customer": customer,
                "points_redeemed": points_to_redeem,
                "redemption_amount": redemption_amount,
                "loyalty_program": loyalty_program,
                "conversion_factor": conversion_factor,
                "loyalty_point_entry": loyalty_point_entry.name,
                "previous_balance": available_points,
                "current_balance": updated_balance,
                "posting_date": loyalty_point_entry.posting_date
            }
        }
        
        create_response("200", response_data)
        return
        
    except Exception as e:
        frappe.db.rollback()
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error redeeming loyalty points")
        return


@frappe.whitelist()
def get_account():
    try:
        # Fetch account details
        accounts = frappe.get_all("Account", 
            filters={
                "account_type": ["in", ["Cash", "Bank"]],
                "is_group": 0

            },
            fields=[
                "name",
                "account_name",
                "account_number",
                "company",
                "parent_account",
                "account_type",
                "account_currency"
            ]
        )
        create_response("200", accounts)
        return

    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching account data")
        return

@frappe.whitelist()
def get_currency_exchange_rate():
    try:
        from erpnext.setup.utils import get_exchange_rate
        
        # Get form data
        data = frappe.local.form_dict
        
        # Get required parameters
        from_currency = data.get("from_currency")
        to_currency = data.get("to_currency")
        transaction_date = data.get("transaction_date")
        args = data.get("args")  # Optional: for_buying/for_selling
        
        # Get exchange rate using ERPNext's utility function
        exchange_rate = get_exchange_rate(
            from_currency=from_currency,
            to_currency=to_currency, 
            transaction_date=transaction_date,
            args=args
        )
        
        create_response("200", {
            "exchange_rate": exchange_rate,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "date": transaction_date
        })
        return
        
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching exchange rate")
        return

@frappe.whitelist()
def create_sales_invoice():
    invoice_data = frappe.local.form_dict
    try:
        si_doc = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": invoice_data.get("customer"),
            "company": invoice_data.get("company"),
            "set_warehouse": invoice_data.get("set_warehouse"),
            "cost_center": invoice_data.get("cost_center"),
            "update_stock": invoice_data.get("update_stock"),
            "posting_date": invoice_data.get("posting_date"),  # Added posting_date
            "posting_time": invoice_data.get("posting_time"),
            "items": [
                {
                    "item_name": item.get("item_name"),
                    "item_code": item.get("item_code"),
                    "rate": item.get("rate"),
                    "qty": item.get("qty"),
                    "cost_center": item.get("cost_center")
                }
                for item in invoice_data.get("items", [])
            ]
        })
        
        si_doc.insert()
        si_doc.submit()
        
        return {
            "status": "success",
            "message": "Sales Invoice created successfully",
            "invoice_name": si_doc.name,
            "created_by": si_doc.owner,
            "created_on": si_doc.creation
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Sales Invoice Creation Error")
        return {
            "status": "error",
            "message": str(e)
        }

@frappe.whitelist()
def create_payment_entry():
    payment_data = frappe.local.form_dict
    try:
        # Create Payment Entry document using frappe.client.insert
        pe_doc = frappe.new_doc({
            "doctype": "Payment Entry",
            "payment_type": payment_data.get("payment_type"),
            "company": payment_data.get("company"),
            "mode_of_payment": payment_data.get("mode_of_payment"),
            "party_type": payment_data.get("party_type"),
            "party": payment_data.get("party"),
            "paid_to_account_currency": payment_data.get("paid_to_account_currency"),
            "paid_to": payment_data.get("paid_to"),
            "paid_amount": payment_data.get("paid_amount"),
            "received_amount": payment_data.get("received_amount"),
            "target_exchange_rate": payment_data.get("target_exchange_rate"),
            "reference_date": payment_data.get("reference_date"),
            "reference_no": payment_data.get("reference_no"),
            "references": [
                {
                    "reference_doctype": payment_data.get("reference_doctype"),
                    "reference_name": payment_data.get("reference_name"),
                    "allocated_amount": payment_data.get("allocated_amount")
                }
                for ref in payment_data.get("references", [])

            ]
        }).insert()
        
        # Submit the Payment Entry document
        pe_doc.submit()
        
        # Return the response
        return {
            "status": "success",
            "message": "Payment Entry created successfully",
            "payment_entry": pe_doc
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Payment Entry Creation Error")
        return {
            "status": "error",
            "message": str(e)
        }

def submit_pos_opening_entry(doc,method):
    # Submit POS Opening Entry document
    doc.submit()

def submit_pos_closing_entry(doc, method=None):
    # Submit POS Closing Entry document
    doc.submit()

def submit_pos_invoice(doc, method=None):
    # Submit POS Invoice document
    doc.submit()

def submit_payment_entry(doc, method=None):
    # Submit Payment Entry document
    doc.submit()

def submit_sales_invoice(doc, method=None):
    # Submit Sales Invoice document
    doc.submit()

@frappe.whitelist()
def get_havano_mobile():
    """API to get the Super User PIN from Havano Mobile single doctype."""
    try:
        doc = frappe.get_single("Havano Mobile")
        pin = doc.super_user_pin if hasattr(doc, "super_user_pin") else None
        if pin is not None:
            create_response("200", {"super_user_pin": pin})
        else:
            create_response("404", {"error": "Super User PIN not found"})
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error fetching Super User PIN")
    return

@frappe.whitelist(allow_guest=False)
def update_havano_mobile(new_pin):
    """API to update the Super User PIN in Havano Mobile single doctype."""
    try:
        if not new_pin:
            create_response("417", {"error": "New PIN is required"})
            return
        frappe.db.set_value("Havano Mobile", "Havano Mobile", "super_user_pin", new_pin)
        frappe.db.commit()
        create_response("200", {"message": "Super User PIN updated successfully"})
    except Exception as e:
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error updating Super User PIN")
    return


@frappe.whitelist()
def create_customer():
    try:
        data = frappe.local.form_dict

        # Required fields for Customer creation
        required_fields = ["customer_name", "customer_type", "customer_email", "customer_phone_number", "customer_tin", "customer_vat"]
        for field in required_fields:
            if not data.get(field):
                create_response("417", {"error": f"Missing required field: {field}"})
                return

        # Create Customer
        customer_doc = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": data.get("customer_name"),
            "customer_type": data.get("customer_type"),
            # "company": data.get("company"),
            "customer_email": data.get("customer_email", ""),
            "customer_tin": data.get("customer_tin", ""),
            "customer_vat": data.get("customer_vat", ""),
            "customer_phone_number": data.get("customer_phone_number", ""),
            "custom_trade_name": data.get("custom_trade_name", ""),
            # Add more fields as needed
        })
        customer_doc.insert()
        frappe.db.commit()

        # Assign User Permission to the logged-in user
        # user = frappe.session.user
        # permission_doc = frappe.get_doc({
        #     "doctype": "User Permission",
        #     "user": user,
        #     "allow": "Customer",
        #     "for_value": customer_doc.name,
        #     "apply_to_all_doctypes": 1
        # })
        # permission_doc.insert()
        # frappe.db.commit()

        create_response("200", {
            "message": "Customer created successfully",
            "customer": customer_doc.name,
            # "user_permission": permission_doc.name
        })
        return

    except Exception as e:
        frappe.db.rollback()
        create_response("417", {"error": str(e)})
        frappe.log_error(message=str(e), title="Error creating customer and assigning permission")
        return