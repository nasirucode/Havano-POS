import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import CustomField

def update_employee():
    """
    Create all custom fields in the Employee doctype
    """
    try:
        frappe.msgprint(_("Starting to create custom fields for Employee doctype..."))
        
        # List of custom fields to create
        custom_fields = [
            {
                "dt": "Employee",
                "fieldname": "custom_salary_structure",
                "label": "Custom Salary Structure",
                "fieldtype": "Link",
                "options": "Salary Structure",
                "insert_after": "salary_mode",
                "description": "Custom salary structure for the employee"
            },
            {
                "dt": "Employee",
                "fieldname": "custom_salary_computed",
                "label": "Custom Salary Computed",
                "fieldtype": "Check",
                "insert_after": "custom_salary_structure",
                "description": "Indicates if custom salary has been computed"
            },
            {
                "dt": "Employee",
                "fieldname": "custom_income_tax_slab",
                "label": "Custom Income Tax Slab",
                "fieldtype": "Link",
                "options": "Income Tax Slab",
                "insert_after": "custom_salary_computed",
                "description": "Custom income tax slab for the employee"
            },
            {
                "dt": "Employee",
                "fieldname": "custom_salary_from_date",
                "label": "Custom Salary From Date",
                "fieldtype": "Date",
                "insert_after": "custom_income_tax_slab",
                "description": "Date from which custom salary structure is effective"
            },
            {
                "dt": "Employee",
                "fieldname": "custom_update_salary",
                "label": "Custom Update Salary",
                "fieldtype": "Select",
                "options": "Yes\nNo",
                "default": "No",
                "insert_after": "custom_salary_from_date",
                "description": "Whether to update salary structure when cancelled"
            }
        ]
        
        # Create custom fields
        created_fields = []
        for field_data in custom_fields:
            try:
                # Check if field already exists
                existing_field = frappe.db.get_value(
                    "Custom Field",
                    {"dt": field_data["dt"], "fieldname": field_data["fieldname"]},
                    "name"
                )
                
                if existing_field:
                    frappe.msgprint(_("Custom field {0} already exists").format(field_data["fieldname"]))
                    continue
                
                # Create the custom field
                custom_field = frappe.new_doc("Custom Field")
                for key, value in field_data.items():
                    custom_field.set(key, value)
                
                custom_field.save()
                created_fields.append(field_data["fieldname"])
                frappe.msgprint(_("Created custom field: {0}").format(field_data["fieldname"]))
                
            except Exception as e:
                frappe.log_error(f"Error creating custom field {field_data['fieldname']}: {str(e)}", 
                                "Custom Field Creation Error")
                frappe.msgprint(_("Error creating custom field {0}: {1}").format(field_data["fieldname"], str(e)))
                continue
        
        # Create child table custom fields
        child_table_fields = [
            {
                "dt": "Employee",
                "fieldname": "custom_earnings",
                "label": "Custom Earnings",
                "fieldtype": "Table",
                "options": "Salary Detail",
                "insert_after": "custom_update_salary",
                "description": "Custom earnings for the employee"
            },
            {
                "dt": "Employee",
                "fieldname": "custom_deductions",
                "label": "Custom Deductions",
                "fieldtype": "Table",
                "options": "Salary Detail",
                "insert_after": "custom_earnings",
                "description": "Custom deductions for the employee"
            },
            {
                "dt": "Employee",
                "fieldname": "custom_additional_salary",
                "label": "Custom Additional Salary",
                "fieldtype": "Table",
                "options": "Additional Salary Table",
                "insert_after": "custom_deductions",
                "description": "Custom additional salary for the employee"
            }
        ]
        
        # Create child table custom fields
        for field_data in child_table_fields:
            try:
                # Check if field already exists
                existing_field = frappe.db.get_value(
                    "Custom Field",
                    {"dt": field_data["dt"], "fieldname": field_data["fieldname"]},
                    "name"
                )
                
                if existing_field:
                    frappe.msgprint(_("Child table custom field {0} already exists").format(field_data["fieldname"]))
                    continue
                
                # Create the custom field
                custom_field = frappe.new_doc("Custom Field")
                for key, value in field_data.items():
                    custom_field.set(key, value)
                
                custom_field.save()
                created_fields.append(field_data["fieldname"])
                frappe.msgprint(_("Created child table custom field: {0}").format(field_data["fieldname"]))
                
            except Exception as e:
                frappe.log_error(f"Error creating child table custom field {field_data['fieldname']}: {str(e)}", 
                                "Child Table Custom Field Creation Error")
                frappe.msgprint(_("Error creating child table custom field {0}: {1}").format(field_data["fieldname"], str(e)))
                continue
        
        frappe.msgprint(_("Successfully created {0} custom fields").format(len(created_fields)))
        
        # Clear cache to reflect changes
        frappe.clear_cache()
        
        return {
            "status": "success",
            "created_fields": created_fields,
            "total_created": len(created_fields)
        }
        
    except Exception as e:
        frappe.log_error(f"Error in update_employee function: {str(e)}", "Update Employee Custom Fields Error")
        frappe.throw(_("Error creating custom fields: {0}").format(str(e)))

def create_custom_doctypes():
    """
    Create the custom doctypes needed for child tables
    """
    try:
        frappe.msgprint(_("Creating custom doctypes for child tables..."))
        
        # Create Salary Component doctype
        create_employee_custom_earnings()
        
        # Create Salary Component doctype
        create_employee_custom_deductions()
        
        # Create Employee Custom Additional Salary doctype
        create_employee_custom_additional_salary()
        
        frappe.msgprint(_("Custom doctypes created successfully"))
        
    except Exception as e:
        frappe.log_error(f"Error creating custom doctypes: {str(e)}", "Custom Doctype Creation Error")
        frappe.throw(_("Error creating custom doctypes: {0}").format(str(e)))

def create_employee_custom_earnings():
    """Create Salary Component doctype"""
    try:
        if frappe.db.exists("DocType", "Salary Component"):
            frappe.msgprint(_("Salary Component doctype already exists"))
            return
        
        # Create the doctype
        doc = frappe.new_doc("DocType")
        doc.name = "Salary Component"
        doc.module = "Havano POS Integration"
        doc.custom = 1
        doc.istable = 1
        doc.issingle = 0
        doc.istransaction = 0
        
        # Add fields
        fields = [
            {
                "fieldname": "salary_component",
                "label": "Salary Component",
                "fieldtype": "Link",
                "options": "Salary Component",
                "reqd": 1,
                "in_standard_filter": 1
            },
            {
                "fieldname": "amount",
                "label": "Amount",
                "fieldtype": "Currency",
                "reqd": 0
            },
            {
                "fieldname": "formula",
                "label": "Formula",
                "fieldtype": "Data",
                "reqd": 0,
                "description": "Formula for calculating the amount"
            },
            {
                "fieldname": "condition",
                "label": "Condition",
                "fieldtype": "Data",
                "reqd": 0,
                "description": "Condition for applying this earning"
            }
        ]
        
        for field_data in fields:
            field = doc.append("fields", field_data)
        
        doc.save()
        frappe.msgprint(_("Created Salary Component doctype"))
        
    except Exception as e:
        frappe.log_error(f"Error creating Salary Component doctype: {str(e)}", 
                        "Custom Doctype Creation Error")
        frappe.throw(_("Error creating Salary Component doctype: {0}").format(str(e)))

def create_employee_custom_deductions():
    """Create Salary Component doctype"""
    try:
        if frappe.db.exists("DocType", "Salary Component"):
            frappe.msgprint(_("Salary Component doctype already exists"))
            return
        
        # Create the doctype
        doc = frappe.new_doc("DocType")
        doc.name = "Salary Component"
        doc.module = "Havano POS Integration"
        doc.custom = 1
        doc.istable = 1
        doc.issingle = 0
        doc.istransaction = 0
        
        # Add fields
        fields = [
            {
                "fieldname": "salary_component",
                "label": "Salary Component",
                "fieldtype": "Link",
                "options": "Salary Component",
                "reqd": 1,
                "in_standard_filter": 1
            },
            {
                "fieldname": "amount",
                "label": "Amount",
                "fieldtype": "Currency",
                "reqd": 0
            },
            {
                "fieldname": "formula",
                "label": "Formula",
                "fieldtype": "Data",
                "reqd": 0,
                "description": "Formula for calculating the amount"
            },
            {
                "fieldname": "condition",
                "label": "Condition",
                "fieldtype": "Data",
                "reqd": 0,
                "description": "Condition for applying this deduction"
            }
        ]
        
        for field_data in fields:
            field = doc.append("fields", field_data)
        
        doc.save()
        frappe.msgprint(_("Created Salary Component doctype"))
        
    except Exception as e:
        frappe.log_error(f"Error creating Salary Component doctype: {str(e)}", 
                        "Custom Doctype Creation Error")
        frappe.throw(_("Error creating Salary Component doctype: {0}").format(str(e)))

def create_employee_custom_additional_salary():
    """Create Employee Custom Additional Salary doctype"""
    try:
        if frappe.db.exists("DocType", "Employee Custom Additional Salary"):
            frappe.msgprint(_("Employee Custom Additional Salary doctype already exists"))
            return
        
        # Create the doctype
        doc = frappe.new_doc("DocType")
        doc.name = "Employee Custom Additional Salary"
        doc.module = "Havano POS Integration"
        doc.custom = 1
        doc.istable = 1
        doc.issingle = 0
        doc.istransaction = 0
        
        # Add fields
        fields = [
            {
                "fieldname": "salary_component",
                "label": "Salary Component",
                "fieldtype": "Link",
                "options": "Salary Component",
                "reqd": 1,
                "in_standard_filter": 1
            },
            {
                "fieldname": "amount",
                "label": "Amount",
                "fieldtype": "Currency",
                "reqd": 1
            },
            {
                "fieldname": "payroll_date",
                "label": "Payroll Date",
                "fieldtype": "Date",
                "reqd": 1
            },
            {
                "fieldname": "currency",
                "label": "Currency",
                "fieldtype": "Link",
                "options": "Currency",
                "reqd": 0
            },
            {
                "fieldname": "description",
                "label": "Description",
                "fieldtype": "Text",
                "reqd": 0
            },
            {
                "fieldname": "overwrite_salary_structure_amount",
                "label": "Overwrite Salary Structure Amount",
                "fieldtype": "Check",
                "reqd": 0,
                "default": 0
            }
        ]
        
        for field_data in fields:
            field = doc.append("fields", field_data)
        
        doc.save()
        frappe.msgprint(_("Created Employee Custom Additional Salary doctype"))
        
    except Exception as e:
        frappe.log_error(f"Error creating Employee Custom Additional Salary doctype: {str(e)}", 
                        "Custom Doctype Creation Error")
        frappe.throw(_("Error creating Employee Custom Additional Salary doctype: {0}").format(str(e)))

def setup_all():
    """
    Setup all custom fields and doctypes for Employee
    """
    try:
        frappe.msgprint(_("Setting up all custom fields and doctypes for Employee..."))
        
        # First create the custom doctypes
        create_custom_doctypes()
        
        # Then create the custom fields
        result = update_employee()
        
        frappe.msgprint(_("Setup completed successfully!"))
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in setup_all: {str(e)}", "Employee Custom Setup Error")
        frappe.throw(_("Error in setup: {0}").format(str(e)))
