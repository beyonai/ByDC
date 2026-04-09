"""Tests for select_column_parser."""

from datacloud_data_sdk.sql_executor.select_column_parser import extract_select_columns


def test_extract_columns_with_as() -> None:
    sql = "SELECT id AS user_id, name AS user_name FROM users"
    assert extract_select_columns(sql) == ["user_id", "user_name"]


def test_extract_columns_without_as() -> None:
    sql = "SELECT id, name FROM users"
    assert extract_select_columns(sql) == ["id", "name"]


def test_extract_columns_mixed() -> None:
    sql = "SELECT a, b AS col_b, c FROM t"
    assert extract_select_columns(sql) == ["a", "col_b", "c"]


def test_extract_columns_empty_or_invalid() -> None:
    assert extract_select_columns("") == []
    assert extract_select_columns("UPDATE t SET x=1") == []


def test_extract_columns_outermost_only() -> None:
    """只取最外层返回列：子查询在 FROM 中时，不取子查询的列。"""
    sql = "SELECT a, b FROM (SELECT x, y FROM t) sub"
    assert extract_select_columns(sql) == ["a", "b"]


def test_extract_columns_custom() -> None:
    sql = "SELECT id AS id, customer_name AS customerName, belong_depart AS belongDepart, type AS type, build_content AS buildContent, iwhale_cbm_emp_no AS iwhaleCbmEmpNo, iwhale_cbm_name AS iwhaleCbmName, iwhale_cbm_org_id AS iwhaleCbmOrgId, belong_industry AS belongIndustry, it_investment_scale AS itInvestmentScale, data_year AS dataYear, software_sale_scale AS softwareSaleScale, next_year_predict_scale AS nextYearPredictScale, contract_scale AS contractScale, process AS process, main_business AS mainBusiness, submit_person AS submitPerson, submit_organization AS submitOrganization, business_opportunity_process AS businessOpportunityProcess, customer_tax_id AS customerTaxId, instance_id AS instanceId FROM sales_customer WHERE belong_industry = '企业行业' AND customer_name IS NOT NULL AND customer_name != ''"
    assert extract_select_columns(sql) == [
        "id",
        "customerName",
        "belongDepart",
        "type",
        "buildContent",
        "iwhaleCbmEmpNo",
        "iwhaleCbmName",
        "iwhaleCbmOrgId",
        "belongIndustry",
        "itInvestmentScale",
        "dataYear",
        "softwareSaleScale",
        "nextYearPredictScale",
        "contractScale",
        "process",
        "mainBusiness",
        "submitPerson",
        "submitOrganization",
        "businessOpportunityProcess",
        "customerTaxId",
        "instanceId",
    ]
