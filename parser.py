import xml.etree.ElementTree as ET
from pathlib import Path


def get_text(parent, tag):
    el = parent.find(tag)
    return el.text if el is not None else None


def get_nested_text(parent, path):
    current = parent
    for tag in path:
        if current is None:
            return None
        current = current.find(tag)
    return current.text if current is not None else None


def parse_form4(xml_path: Path) -> list:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    print(f"Parsing {xml_path.name}  root=<{root.tag}>")

    schema_version           = get_text(root, "schemaVersion")
    document_type            = get_text(root, "documentType")
    period_of_report         = get_text(root, "periodOfReport")
    not_subject_to_section16 = get_text(root, "notSubjectToSection16")

    issuer        = root.find("issuer")
    issuer_cik    = get_text(issuer, "issuerCik")
    issuer_name   = get_text(issuer, "issuerName")
    issuer_ticker = get_text(issuer, "issuerTradingSymbol")

    reporting_owner              = root.find("reportingOwner")
    reporting_owner_id           = reporting_owner.find("reportingOwnerId")
    reporting_owner_relationship = reporting_owner.find("reportingOwnerRelationship")

    reporting_owner_cik  = get_text(reporting_owner_id, "rptOwnerCik")
    reporting_owner_name = get_text(reporting_owner_id, "rptOwnerName")

    is_director          = get_text(reporting_owner_relationship, "isDirector")
    is_officer           = get_text(reporting_owner_relationship, "isOfficer")
    is_ten_percent_owner = get_text(reporting_owner_relationship, "isTenPercentOwner")
    is_other             = get_text(reporting_owner_relationship, "isOther")
    officer_title        = get_text(reporting_owner_relationship, "officerTitle")
    other_text           = get_text(reporting_owner_relationship, "otherText")

    non_derivative_table = root.find("nonDerivativeTable")
    if non_derivative_table is None:
        print(f"  ⚠ No nonDerivativeTable in {xml_path.name}, skipping")
        return []

    rows = []
    for tx in non_derivative_table.findall("nonDerivativeTransaction"):
        rows.append({
            "source_file"                      : xml_path.name,
            "security_title"                   : get_nested_text(tx, ["securityTitle", "value"]),
            "transaction_date"                 : get_nested_text(tx, ["transactionDate", "value"]),
            "transaction_form_type"            : get_nested_text(tx, ["transactionCoding", "transactionFormType"]),
            "transaction_code"                 : get_nested_text(tx, ["transactionCoding", "transactionCode"]),
            "equity_swap_involved"             : get_nested_text(tx, ["transactionCoding", "equitySwapInvolved"]),
            "transaction_shares"               : get_nested_text(tx, ["transactionAmounts", "transactionShares", "value"]),
            "transaction_price_per_share"      : get_nested_text(tx, ["transactionAmounts", "transactionPricePerShare", "value"]),
            "transaction_acquired_disposed_code": get_nested_text(tx, ["transactionAmounts", "transactionAcquiredDisposedCode", "value"]),
            "shares_owned_following_transaction": get_nested_text(tx, ["postTransactionAmounts", "sharesOwnedFollowingTransaction", "value"]),
            "direct_or_indirect_ownership"     : get_nested_text(tx, ["ownershipNature", "directOrIndirectOwnership", "value"]),
            "nature_of_ownership"              : get_nested_text(tx, ["ownershipNature", "natureOfOwnership", "value"]),
            "schema_version"                   : schema_version,
            "document_type"                    : document_type,
            "period_of_report"                 : period_of_report,
            "not_subject_to_section16"         : not_subject_to_section16,
            "issuer_cik"                       : issuer_cik,
            "issuer_name"                      : issuer_name,
            "issuer_ticker"                    : issuer_ticker,
            "reporting_owner_cik"              : reporting_owner_cik,
            "reporting_owner_name"             : reporting_owner_name,
            "is_director"                      : is_director,
            "is_officer"                       : is_officer,
            "is_ten_percent_owner"             : is_ten_percent_owner,
            "is_other"                         : is_other,
            "officer_title"                    : officer_title,
            "other_text"                       : other_text,
        })

    return rows

