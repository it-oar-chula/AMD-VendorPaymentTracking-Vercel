import os
import sys
from pathlib import Path

os.environ.setdefault("API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from api import index


def sample_payment_df():
    df = pd.DataFrame(
        [
            {
                "วันที่รายการมีผล": "25-มิ.ย.-2569",
                "เลขที่อ้างอิงผู้รับเงิน": "2026/2350000923",
                "บัญชีผู้รับเงิน": "1234567890",
                "ชื่อผู้รับเงิน": "จุฬาลงกรณ์มหาวิทยาลัย",
                "ธนาคาร": "KBANK - ธ. กสิกรไทย",
                "สาขาธนาคารผู้รับเงิน": "สาขาสยามสแควร์",
                "จำนวนเงิน": "64998.5",
                "รายละเอียดของรายการ": "HRPAY 6000002840",
                "สถานะรายการ": "ดำเนินการสำเร็จ",
            },
            {
                "วันที่รายการมีผล": "25-มิ.ย.-2569",
                "เลขที่อ้างอิงผู้รับเงิน": "2026/2350000922",
                "บัญชีผู้รับเงิน": "0191656636",
                "ชื่อผู้รับเงิน": "ผู้รับเงินอื่น",
                "ธนาคาร": "KBANK - ธ. กสิกรไทย",
                "สาขาธนาคารผู้รับเงิน": "สาขาสยามสแควร์",
                "จำนวนเงิน": "96200",
                "รายละเอียดของรายการ": "HRPAY 6000002749",
                "สถานะรายการ": "ดำเนินการสำเร็จ",
            },
        ]
    )
    df["Payment_Document_Number"] = df[index.PAYMENT_REFERENCE_COLUMN].astype(str).str.split("/").str[-1].str.strip()
    df["Payment_Document_Number_Normalized"] = df["Payment_Document_Number"].apply(index.normalize_identifier)
    return df


def sample_tax_df():
    df = pd.DataFrame(
        [
            {
                "เลขที่ภาษี 3": "3100200097940",
                "เลขเอกสาร": "2350000923",
                "ชื่อ 1": "จุฬาลงกรณ์มหาวิทยาลัย",
            },
            {
                "เลขที่ภาษี 3": "3100700751193",
                "เลขเอกสาร": "2350000922",
                "ชื่อ 1": "ผู้รับเงินอื่น",
            },
        ]
    )
    df["Tax_ID_Normalized"] = df[index.TAX_ID_COLUMN].apply(index.normalize_identifier)
    df["Tax_Document_Number"] = df[index.TAX_DOCUMENT_COLUMN].astype(str).str.strip()
    df["Tax_Document_Number_Normalized"] = df["Tax_Document_Number"].apply(index.normalize_identifier)
    return df


if __name__ == "__main__":
    payment_df = sample_payment_df()
    tax_df = sample_tax_df()

    assert index.validate_tax_id_query("3100200097940") == ("3100200097940", None)
    assert index.validate_tax_id_query("310 0200 097 940") == ("3100200097940", None)
    assert index.validate_tax_id_query("310020009794")[1].startswith("เลขประจำตัวผู้เสียภาษียังไม่ครบ")
    assert index.validate_tax_id_query("31002000979401")[1].startswith("เลขประจำตัวผู้เสียภาษีเกิน")
    assert index.validate_tax_id_query("310020009794A")[1] == "เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลข 13 หลักเท่านั้น"

    result = index.tax_id_payment_search(payment_df, tax_df, "3100200097940")
    assert result is not None
    assert result[index.PAYMENT_REFERENCE_COLUMN].tolist() == ["2026/2350000923"]
    assert result[index.TAX_DOCUMENT_COLUMN].tolist() == ["2350000923"]

    assert index.tax_id_payment_search(payment_df, tax_df, "310020009794").empty
    assert index.tax_id_payment_search(payment_df, tax_df, "จุฬาลงกรณ์").empty

    records = index.payment_records(result, "3100200097940")
    assert records[0]["เลขประจำตัวผู้เสียภาษี"] == "3100200097940"
    assert records[0]["เลขเอกสาร"] == "2350000923"
    assert records[0]["บัญชีผู้รับเงิน"] == "xxxxxx7890"
