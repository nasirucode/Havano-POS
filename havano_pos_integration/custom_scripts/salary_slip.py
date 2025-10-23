import frappe

def validate(doc, method):
    check_duplicate_salary_slip(doc)
    
    # Calculate all components at once
    calculate_components(doc)
    
    # Update final values
    update_total_deductions(doc)

def check_duplicate_salary_slip(doc):
    existing_salary_slip = frappe.db.exists(
        "Salary Slip",
        {
            "employee": doc.employee,
            "start_date": doc.start_date,
            "end_date": doc.end_date,
            "currency": doc.currency,
            "docstatus": ["!=", 2],
            "name": ["!=", doc.name]
        }
    )
    
    if existing_salary_slip:
        frappe.throw(f"Salary Slip already exists for Employee {doc.employee} in Currency {doc.currency} for the given date range")

def calculate_components(doc):
    # Calculate base values first
    total_earnings = sum(earning.amount or 0 for earning in doc.earnings)
    
    # Calculate taxable earnings
    taxable_earnings = 0
    for earning in doc.earnings:
        if frappe.db.get_value('Salary Component', earning.salary_component, 'is_tax_applicable'):
            taxable_earnings += earning.amount or 0
    
    # Get existing components and track them
    component_amounts = {}
    for row in doc.deductions:
        component_amounts[row.salary_component] = row
    
    # Get all needed component rates from structures
    structure = doc.salary_structure
    
    # Define components and their default rates
    tax_components = {
        'NSSA': 0.045,
        'ZIMDEF': 0.01,
        'Aids Levy': 0.03,
        'NEC Commercial': 0.01,
        'NEC Mining': 0.0045,
        'Cimas': 0.25,
        'Funeral Policy': 0.25,
        'UFAWUZ': 0.03,
        'ZiBAWU': 0.02,
        'LAPF': 0.06,
        'ZESCWU': 0.04,
        'NEC Cleaning': 0.01,
        'NECWEI': 0.04,
        'Service Allowance': 0.01
    }
    
    # Fetch all tax rates from Company Tax Calculations
    for component_name in tax_components:
        tax_percentage = frappe.db.get_value("Company Tax Calculations", component_name, "tax_percentage")
        if tax_percentage is not None:
            # Convert percentage to decimal
            tax_components[component_name] = float(tax_percentage) / 100
    
    # Get Medical amount if it exists
    medical_amount = 0
    for component_name, component in component_amounts.items():
        if "MEDICAL" in component_name.upper():
            medical_amount += component.amount or 0
    # Get Basic Salary amount for UFAWUZ calculation
    basic_salary = 0
    for earning in doc.earnings:
        if earning.salary_component == 'Basic Salary' or 'Basic':
            basic_salary = earning.amount or 0
            break

    income_after_medical = taxable_earnings - (medical_amount * 0.5)
    doc.custom_total_taxable_earnings_after_medical = income_after_medical

    # Calculate NSSA based on gross pay
    # if component_exists_in_structure(structure, 'NSSA'):
    #     add_or_update_component(doc, component_amounts, 'NSSA', total_earnings * tax_components['NSSA'])
    # Update NSSA calculation based on nssa_ceiling
    if component_exists_in_structure(structure, 'NSSA'):
        # Fetch nssa_ceiling from Payroll Settings
        nssa_ceiling = frappe.db.get_single_value("Payroll Settings", "nssa_ceiling") or 0

        # Calculate NSSA based on the ceiling
        if total_earnings <= nssa_ceiling:
            nssa_amount = total_earnings * tax_components['NSSA']
        else:
            nssa_amount = nssa_ceiling * tax_components['NSSA']
        # Add or update NSSA component
        add_or_update_component(doc, component_amounts, 'NSSA', nssa_amount)

    # Calculate ZIMDEF based on total earnings
    if component_exists_in_structure(structure, 'ZIMDEF'):
        add_or_update_component(doc, component_amounts, 'ZIMDEF', total_earnings * tax_components['ZIMDEF'])
    
    # Calculate NEC Commercial based on taxable income
    if component_exists_in_structure(structure, 'NEC Commercial'):
        add_or_update_component(doc, component_amounts, 'NEC Commercial', total_earnings * tax_components['NEC Commercial'])
    
     # Calculate NEC Cleaning based on taxable income
    if component_exists_in_structure(structure, 'NEC Cleaning'):
        add_or_update_component(doc, component_amounts, 'NEC Cleaning', total_earnings * tax_components['NEC Cleaning'])
    
    # Calculate NEC Mining based on taxable income
    if component_exists_in_structure(structure, 'NEC Mining'):
        add_or_update_component(doc, component_amounts, 'NEC Mining', total_earnings * tax_components['NEC Mining'])
    
    # Calculate UFAWUZ based on basic salary
    if component_exists_in_structure(structure, 'UFAWUZ'):
        add_or_update_component(doc, component_amounts, 'UFAWUZ', basic_salary * tax_components['UFAWUZ'])

    # Calculate NECWEI based on basic salary
    if component_exists_in_structure(structure, 'NECWEI'):
        add_or_update_component(doc, component_amounts, 'NECWEI', basic_salary * tax_components['NECWEI'])

    # Calculate Service Allowance based on basic salary
    if component_exists_in_structure(structure, 'Service Allowance'):
        add_or_update_earning(doc, component_amounts, 'Service Allowance', basic_salary * tax_components['Service Allowance'])

    # Calculate ZESCWU based on basic salary
    if component_exists_in_structure(structure, 'ZESCWU'):
        add_or_update_component(doc, component_amounts, 'ZESCWU', basic_salary * tax_components['ZESCWU'])

    # Calculate Cimas based on basic salary
    if component_exists_in_structure(structure, 'Cimas'):
        add_or_update_component(doc, component_amounts, 'Cimas', basic_salary * tax_components['Cimas'])
    
    # Calculate ZiBAWU based on basic salary
    if component_exists_in_structure(structure, 'ZiBAWU'):
        add_or_update_component(doc, component_amounts, 'ZiBAWU', basic_salary * tax_components['ZiBAWU'])

    # Calculate LAPF based on basic salary
    if component_exists_in_structure(structure, 'LAPF'):
        add_or_update_component(doc, component_amounts, 'LAPF', basic_salary * tax_components['LAPF'])
    
    # Calculate total allowable deductions using payee_deductions from Payroll Settings
    total_allowable = calculate_total_allowable_from_settings(doc, component_amounts)
    doc.custom_total_allowable_deductions = total_allowable
    
    # Calculate taxable income after allowable deductions
    doc.custom_total_taxable_income = taxable_earnings - total_allowable
    
    # Calculate tax and AIDS Levy
    calculate_tax(doc, component_amounts, tax_components, medical_amount)

def calculate_total_allowable_from_settings(doc, component_amounts):
    """
    Calculate total allowable deductions based on components selected in Payroll Settings payee_deductions
    """
    # Get payee_deductions from Payroll Settings
    payroll_settings = frappe.get_single("Payroll Settings")
    total_allowable = 0
    
    if payroll_settings.payee_deductions:
        for deduction_row in payroll_settings.payee_deductions:
            component_name = deduction_row.component
            # Get the amount for this component from the calculated component_amounts
            component_amount = component_amounts.get(component_name, {}).get('amount', 0) or 0
            total_allowable += component_amount
    
    return total_allowable

def add_or_update_component(doc, component_dict, component_name, amount):
    if component_name in component_dict:
        component_dict[component_name].amount = amount
    else:
        doc.append('deductions', {
            'salary_component': component_name,
            'amount': amount
        })
        component_dict[component_name] = doc.deductions[-1]


def add_or_update_earning(doc, component_dict, component_name, amount):
    if component_name in component_dict:
        component_dict[component_name].amount = amount
    else:
        doc.append('earnings', {
            'salary_component': component_name,
            'amount': amount
        })
        component_dict[component_name] = doc.earnings[-1]

def calculate_tax(doc, component_amounts, tax_components, medical_amount):
    # Get tax slab
    salary_structure_assignment = frappe.get_value(
        "Salary Structure Assignment",
        {
            "employee": doc.employee,
            "salary_structure": doc.salary_structure,
            "docstatus": 1
        },
        "income_tax_slab"
    )
    
    if not salary_structure_assignment:
        return
    
    taxable_income = doc.custom_total_taxable_income
    tax_slab = frappe.get_doc("Income Tax Slab", salary_structure_assignment)
    total_tax = 0
    
    # Find applicable tax slab
    for slab in tax_slab.slabs:
        if (taxable_income >= slab.from_amount and 
            (taxable_income <= slab.to_amount or not slab.to_amount)):
            tax = (taxable_income * (slab.percent_deduction / 100)) - slab.custom_amount_deduction - (medical_amount * 0.5)
            total_tax = tax
            break
    
    # Add or update PAYEE
    if component_exists_in_structure(doc.salary_structure, 'Payee'):
        add_or_update_component(doc, component_amounts, 'Payee', total_tax)
    
    # Add or update AIDS Levy
    if component_exists_in_structure(doc.salary_structure, 'Aids Levy'):
        add_or_update_component(doc, component_amounts, 'Aids Levy', total_tax * tax_components['Aids Levy'])

def update_total_deductions(doc):
    doc.total_deduction = sum(row.amount or 0 for row in doc.deductions)

    doc.net_pay = doc.gross_pay - doc.total_deduction
    doc.base_net_pay = doc.net_pay * (doc.exchange_rate or 1)

def component_exists_in_structure(salary_structure, component_name):
    return frappe.db.exists({
        'doctype': 'Salary Detail',
        'parent': salary_structure,
        'salary_component': component_name,
        'parenttype': 'Salary Structure'
    })