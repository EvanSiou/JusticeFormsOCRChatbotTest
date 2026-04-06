"""Seed default configuration, prompts, and form types into DynamoDB."""
import logging
from . import dynamodb

logger = logging.getLogger(__name__)

DEFAULT_OCR_PROMPT = (
    "Extract ALL text from this document image. "
    "Return every word exactly as it appears, preserving line breaks. "
    "Do not add any commentary, formatting, or markdown — only the raw text content."
)

# The full Prisoner Registration classification prompt from eCourtDateOCR
PRISONER_REG_CLASSIFICATION_PROMPT = """You are analyzing a Prisoner Registration Form. Use BOTH the image and the OCR text below to extract specific data fields.

FORM STRUCTURE:
This is a 2-page form with the following sections:
- Page 1: Officer Registration, Prisoner Information, Additional Identifiers, Scars/Marks/Tattoos, Address, Telephone, Emergency Contacts, Employer
- Page 2: Arrest Information, Officer Details, Property Inventory, Secure Packs

FIELDS TO EXTRACT:

SECTION: ARRESTING OFFICER
- officer_type: [Arresting | Transporting | Both] (CHECKBOX)
- officer_last_name: Officer's last name
- officer_first_name: Officer's first name
- badge_number: Badge number
- employee_id_number: Employee ID
- contact_phone_number: Contact phone
- agency: Agency name

SECTION: PRISONER INFORMATION
- first_name: Prisoner's first name
- last_name: Prisoner's last name
- middle_name: Prisoner's middle name
- ssn: Social Security Number
- date_of_birth: Date of birth
- age: Age in years
- sex: [M | F] (CHECKBOX)
- race: Race
- ethnicity: [Hispanic | Non-Hispanic] (CHECKBOX)
- citizenship: Citizenship
- country_of_birth: Country of birth
- city_of_birth: City of birth
- height: Height
- weight: Weight
- eyes: Eye color
- skin: Skin tone
- hair_type: Hair type
- hair_length: Hair length
- hair_color: Hair color
- build: [Skinny | Light | Medium | Heavy | Obese] (CHECKBOX)
- beard: [Heavy | Medium | Thin | Goatee | None] (CHECKBOX)
- mustache: [Y | N] (CHECKBOX)
- glasses: [Y | N] (CHECKBOX)
- marital_status: Marital status
- religious_preference: Religious preference
- veteran: [Y | N] (CHECKBOX)
- using_drugs: [Y | N] (CHECKBOX)
- using_alcohol: [Y | N] (CHECKBOX)
- wanted: [Y | N] (CHECKBOX)
- agency_wanting_person: Agency wanting person
- agency_contact_person: Agency contact person

SECTION: ADDITIONAL IDENTIFIERS
- hcso_spn: HCSO SPN number
- state_issued_id_number: State-issued ID number
- issuing_state: State that issued ID
- drivers_license_number: Driver's license number
- dl_state: Driver's license state
- dl_type: Driver's license type
- sid_number: SID number
- fbi_number: FBI number
- afis_number: AFIS number
- so_number: SO number
- da_log_number: DA log number
- assistant_da_name: Assistant DA name

SECTION: SCARS/MARKS/TATTOOS (up to 3 entries)
- smt_1_type, smt_1_location, smt_1_description
- smt_2_type, smt_2_location, smt_2_description
- smt_3_type, smt_3_location, smt_3_description

SECTION: ADDRESS
- address_type, address_street, address_city, address_state, address_zip, address_source

SECTION: TELEPHONE (up to 2 entries)
- phone_1_type, phone_1_number, phone_1_source
- phone_2_type, phone_2_number, phone_2_source

SECTION: EMERGENCY CONTACT
- emergency_first_name, emergency_middle_name, emergency_last_name
- emergency_relationship, emergency_phone, emergency_source

SECTION: EMPLOYER
- employer_name, occupation, employer_address, employer_city
- employer_state, employer_zip, employer_phone_type, employer_phone, employer_source

SECTION: ARREST INFORMATION (Page 2)
- arrest_date, arrest_time, arrest_location, arresting_agency
- prisoner_health_condition
- unusual_behavior: [Yes | No] (CHECKBOX)

SECTION: ARRESTING OFFICER (Page 2)
- arr_officer_last_name, arr_officer_first_name, arr_officer_badge
- arr_officer_employee_id, arr_officer_contact, arr_officer_unit, arr_officer_agency

SECTION: TRANSPORTING OFFICER
- trans_officer_last_name, trans_officer_first_name, trans_officer_badge
- trans_officer_employee_id, trans_officer_contact, trans_officer_unit, trans_officer_agency

SECTION: PROPERTY
- valuable_property, bulk_property, clothing_property, other_property

SECTION: SECURE PACKS
- secure_pack_quantity
- phone_numbers_opportunity: [Yes | No] (CHECKBOX)
- prisoner_signature: [present | absent]
- officer_signature: [present | absent]

EXTRACTION RULES:
1. Checkboxes: Return ONLY the selected option text (e.g., "M" not "box M")
2. Handwritten text: Transcribe exactly, note [illegible] for unreadable
3. Empty fields = null
4. Confidence: 1.0=clear, 0.8-0.9=legible handwriting, 0.6-0.7=partial, 0.3-0.5=difficult
5. Signatures: Return "present" or "absent" only

OCR TEXT:
---
{ocr_text}
---

Return ONLY valid JSON (no markdown, no code fences) with "fields" dict where each field has "value" and "confidence"."""

AFFIDAVIT_CLASSIFICATION_PROMPT = """You are analyzing an Affidavit of Financial Condition form. Use BOTH the image and the OCR text below to extract specific data fields.

FORM STRUCTURE:
This is a multi-page form covering: Personal info, Financial assets, Debts, Income, Expenses, Employment history, Bond information.

FIELDS TO EXTRACT:
- cause_number: Case/cause number
- spn_number: SPN number
- defendant_name: Defendant's full name
- phone_number: Phone number
- address: Full address
- date_of_birth: Date of birth
- city_state: City and state
- zip_code: ZIP code
- marital_status: Marital status and dependents
- cash_total_myself: Total cash available (myself)
- cash_total_spouse: Total cash available (spouse)
- bond_amount: Amount of bond
- bond_payer: Name of person who paid for bond
- attorney_status: Represented or not represented
- signature_date: Date of signature
- defendant_signature: [present | absent]

EXTRACTION RULES:
1. Extract ACTUAL filled-in values, not template labels
2. Empty fields = null
3. Confidence: 1.0=clear, 0.8-0.9=legible, 0.6-0.7=partial, 0.3-0.5=difficult

OCR TEXT:
---
{ocr_text}
---

Return ONLY valid JSON (no markdown) with "fields" dict where each field has "value" and "confidence"."""


def seed_defaults():
    """Seed default data into DynamoDB if not already present."""
    config = dynamodb.get_config()
    if config.get("_seeded"):
        logger.info("Default data already seeded")
        return

    logger.info("Seeding default data...")

    # Default config
    dynamodb.save_config({
        "config_key": "global",
        "quality_threshold": 0.6,
        "default_model": "claude_bedrock",
        "_seeded": True,
    })

    # Default prompts
    ocr_prompt = dynamodb.create_prompt({
        "name": "Default OCR Prompt",
        "prompt_type": "ocr",
        "prompt_text": DEFAULT_OCR_PROMPT,
        "form_type": None,
    })

    pr_prompt = dynamodb.create_prompt({
        "name": "Prisoner Registration Form v1",
        "prompt_type": "classification",
        "prompt_text": PRISONER_REG_CLASSIFICATION_PROMPT,
        "form_type": "prisoner_registration",
    })

    af_prompt = dynamodb.create_prompt({
        "name": "Affidavit of Financial Condition v1",
        "prompt_type": "classification",
        "prompt_text": AFFIDAVIT_CLASSIFICATION_PROMPT,
        "form_type": "affidavit_financial",
    })

    # Form types
    dynamodb.create_form_type({
        "form_type_id": "prisoner_registration",
        "display_name": "JMS Prisoner Registration Form",
        "page_count": 2,
        "html_template_name": "prisoner_registration.html",
        "default_classification_prompt_id": pr_prompt["prompt_id"],
    })

    dynamodb.create_form_type({
        "form_type_id": "affidavit_financial",
        "display_name": "Affidavit of Financial Condition",
        "page_count": 6,
        "html_template_name": "affidavit_financial.html",
        "default_classification_prompt_id": af_prompt["prompt_id"],
    })

    # Update config with default prompt IDs
    dynamodb.save_config({
        "config_key": "global",
        "quality_threshold": 0.6,
        "default_model": "claude_bedrock",
        "default_ocr_prompt_id": ocr_prompt["prompt_id"],
        "_seeded": True,
    })

    logger.info("Default data seeded successfully")
