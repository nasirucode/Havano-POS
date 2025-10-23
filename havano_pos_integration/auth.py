import frappe
from frappe import _
from frappe.utils import escape_html,cstr
from frappe.auth import LoginManager
from frappe import throw, msgprint, _
from frappe.utils.background_jobs import enqueue
import requests
import random
import json
import base64
from havano_pos_integration.utils import create_response
from tzlocal import get_localzone
import pytz


@frappe.whitelist(allow_guest=True)
def login(usr,pwd, timezone):
    

    local_tz = str(get_localzone())
    erpnext_tz = frappe.utils.get_system_timezone()

    if timezone != erpnext_tz:
        frappe.local.response.http_status_code = 400
        frappe.local.response["message"] = f"Timezone mismatch. Your timezone is {timezone}, but system requires {erpnext_tz}"
        return

    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr,pwd=pwd)
        login_manager.post_login()
    except frappe.exceptions.AuthenticationError:
        frappe.clear_messages()
        frappe.local.response.http_status_code = 422
        frappe.local.response["message"] =  "Invalid Email or Password"
        return

    if usr == "Administrator":
        execute()
        enable_allow_negative_stock()
    
    user = frappe.get_doc('User',frappe.session.user)

    api_generate=generate_keys(user)
       
    token_string = str(api_generate['api_key']) +":"+ str(api_generate['api_secret'])

    # Get user permissions for warehouse and cost center
    warehouses = frappe.get_list("User Permission", 
        filters={
            "user": user.name,
            "allow": "Warehouse"
        },
        pluck="for_value"
    )
    
    cost_centers = frappe.get_list("User Permission",
        filters={
            "user": user.name, 
            "allow": "Cost Center"
        },
        pluck="for_value"
    )
    default_warehouse = frappe.db.get_value("User Permission", 
        {"user": user.name, "allow": "Warehouse", "is_default": 1}, "for_value")
    
    default_cost_center = frappe.db.get_value("User Permission",
        {"user": user.name, "allow": "Cost Center", "is_default": 1}, "for_value")

    default_customer = frappe.db.get_value("User Permission",
        {"user": user.name, "allow": "Customer", "is_default": 1}, "for_value") 

    # Get items and their quantities from all warehouses
    warehouse_items = []
    if default_warehouse:
        warehouse_items = frappe.db.sql("""
            SELECT 
                item.item_code,
                item.item_name,
                item.description,
                item.stock_uom,
                bin.actual_qty,
                bin.projected_qty
            FROM `tabItem` item
            LEFT JOIN `tabBin` bin ON bin.item_code = item.item_code 
            WHERE bin.warehouse = %s
        """, default_warehouse, as_dict=1)

    # Get customer group permissions from user permissions
    customer_groups = frappe.get_list("User Permission", 
        filters={
            "user": user.name,
            "allow": "Customer Group"
        },
        pluck="for_value"
    )
    
    warehouse_items = frappe.db.sql("""
        SELECT 
            item.item_code,
            item.item_name,
            item.description,
            item.stock_uom,
            bin.actual_qty,
            bin.projected_qty
        FROM `tabItem` item
        LEFT JOIN `tabBin` bin ON bin.item_code = item.item_code 
    """, as_dict=1)
        
        # Add pricing information to warehouse items
    default_price_list = frappe.db.get_value("Customer", default_customer, "default_price_list")

    if default_customer:
        try:
            # Get the default selling price list
            if not default_price_list:
                # Fallback to any selling price list
                default_price_list = frappe.db.get_value("Price List", {"selling": 1}, "name")
            
            if default_price_list:
                # Get the company and its default currency
                default_company = frappe.db.get_single_value('Global Defaults', 'default_company')
                company_currency = frappe.db.get_value("Company", default_company, "default_currency") if default_company else None
                
                for item in warehouse_items:
                    try:
                        from erpnext.stock.get_item_details import get_item_details
                        
                        # Get item details with customer context
                        item_details = get_item_details({
                            "doctype": "Sales Invoice",
                            "item_code": item.item_code,
                            "company": default_company,
                            "customer": default_customer,
                            "selling_price_list": default_price_list,
                            "qty": 1,
                            "currency": company_currency,
                            "conversion_rate": 1.0,
                            "plc_conversion_rate": 1.0
                        })
                        
                        # Add pricing fields to the existing item
                        item["price_list_rate"] = item_details.get("price_list_rate", 0)
                        item["rate"] = item_details.get("rate", 0)
                        item["currency"] = frappe.db.get_value("Price List", default_price_list, "currency") or company_currency
                        
                    except Exception as e:
                        # If there's an error getting price for specific item, set default values
                        error_msg = f"Error getting price for item {item.item_code}: {str(e)}"
                        if len(error_msg) > 140:
                            error_msg = error_msg[:137] + "..."
                        frappe.log_error(error_msg, "Item Price Error")
                        item["price_list_rate"] = 0
                        item["rate"] = 0
                        item["currency"] = company_currency
        except Exception as e:
            error_msg = f"Error getting item prices: {str(e)}"
            if len(error_msg) > 140:
                error_msg = error_msg[:137] + "..."
            frappe.log_error(error_msg, "Item Prices Error")
            # Set default values for all items if there's a general error
            for item in warehouse_items:
                item["price_list_rate"] = 0
                item["rate"] = 0
                item["currency"] = None
    else:
        # If no default customer, set default pricing values
        for item in warehouse_items:
            item["price_list_rate"] = 0
            item["rate"] = 0
            item["currency"] = None

    # Get customers with the same cost center as the default cost center
    customers = []
    if default_cost_center:
        customers = frappe.get_list("Customer",
            filters={
                "custom_cost_center": default_cost_center
            },
            fields=["name", "customer_name", "customer_group", "territory", "custom_cost_center"]
        )
    
    # If no customers found, try filtering by customer group from user permissions
    if customer_groups:
        customers = frappe.get_list("Customer",
            filters={
                "customer_group": ["in", customer_groups]
            },
            fields=["name", "customer_name", "customer_group", "territory", "custom_cost_center", "default_price_list"]
        )
    
    # If still no customers found, try using cost center as customer group (fallback)
    if not customers:
        customers = frappe.get_list("Customer",
            filters={
                "customer_group": default_cost_center
            },
            fields=["name", "customer_name", "customer_group", "territory", "custom_cost_center"]
        )
    
    default_company_doc = None
    default_company = frappe.db.get_single_value('Global Defaults','default_company')
    if default_company:
        default_company_doc = frappe.get_doc("Company" , default_company) 
    
    company_info = {
        "name": default_company_doc.name if default_company_doc else "",
        "email": default_company_doc.email if default_company_doc else "",
        "website": default_company_doc.website if default_company_doc else ""
    }

    frappe.response["user"] =   {
        "first_name": escape_html(user.first_name or ""),
        "last_name": escape_html(user.last_name or ""),
        "gender": escape_html(user.gender or "") or "",
        "birth_date": user.birth_date or "",       
        "mobile_no": user.mobile_no or "",
        "username":user.username or "",
        "full_name":user.full_name or "",
        "email":user.email or "",
        "warehouse": default_warehouse,
        "cost_center": default_cost_center,
        "default_customer": default_customer,
        "customer_default_price_list": default_price_list,
        "total_customers": len(customers),
        "customers": customers,
        "warehouse_items": warehouse_items,
        "time_zone": f"{local_tz}",
        "company" : company_info,
    }
    frappe.response["token_string"] = token_string
    frappe.response["token"] =  base64.b64encode(token_string.encode("ascii")).decode("utf-8")

    return


def generate_keys(user):
    api_secret = api_key = ''
    if not user.api_key and not user.api_secret:
        api_secret = frappe.generate_hash(length=15)
        # if api key is not set generate api key
        api_key = frappe.generate_hash(length=15)
        user.api_key = api_key
        user.api_secret = api_secret
        user.save(ignore_permissions=True)
    else:
        api_secret = user.get_password('api_secret')
        api_key = user.get('api_key')
    return {"api_secret": api_secret, "api_key": api_key}

# For Verfiy OTP Function
@frappe.whitelist(allow_guest=True)
def logout(user):
    try:
        user = frappe.get_doc("User",user)
        user.api_key = None
        user.api_secret = None
        user.save(ignore_permissions = True)
        
        frappe.local.login_manager.logout()
        create_response(200, "Logged Out Successfully")
        return
    except frappe.DoesNotExistError:
        # Handle case where user document is not found
        frappe.log_error(f"User '{user}' does not exist.", "Logout Failed")
        create_response(404, "User not found")
        return
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Logout Failed")
        create_response(417, "Something went wrong", str(e))
        return

def execute():
    if not frappe.db.exists("Custom Field", "Customer-custom_cost_center"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Customer",
            "fieldname": "custom_cost_center",
            "label": "Cost Center",
            "fieldtype": "Link",
            "options": "Cost Center",
            "insert_after": "customer_address"
        }).insert()

    if not frappe.db.exists("Custom Field", "Customer-custom_warehouse"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Customer",
            "fieldname": "custom_warehouse",
            "label": "Warehouse",
            "fieldtype": "Link",
            "options": "Cost Center",
            "insert_after": "customer_address"
        }).insert()

def enable_allow_negative_stock():
    try:
        stock_settings = frappe.get_doc("Stock Settings")
        stock_settings.allow_negative_stock = 1
        stock_settings.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "message": _("Allow Negative Stock enabled.")}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Enable Allow Negative Stock Error")
        return {"status": "error", "message": str(e)}