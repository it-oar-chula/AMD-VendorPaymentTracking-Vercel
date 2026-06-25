import os
import sys
from pathlib import Path

os.environ.setdefault("API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from api import index


def sample_df():
    return pd.DataFrame(
        [
            {
                "Invoice_Number": "INV001",
                "Invoice_Number_Upper": "INV001",
                "ชื่อผู้รับเงิน": "บริษัท ตัวอย่าง จำกัด",
                "รายละเอียดของรายการ": "INV001 ค่าบริการรายเดือน",
            },
            {
                "Invoice_Number": "INV002",
                "Invoice_Number_Upper": "INV002",
                "ชื่อผู้รับเงิน": "ห้างหุ้นส่วน ทดสอบ",
                "รายละเอียดของรายการ": "INV002 งานซ่อม",
            },
        ]
    )


if __name__ == "__main__":
    df = sample_df()

    strict_invoice = index.strict_invoice_or_company_search(df, "INV001")
    assert strict_invoice is not None
    assert strict_invoice["ชื่อผู้รับเงิน"].tolist() == ["บริษัท ตัวอย่าง จำกัด"]

    strict_company = index.strict_invoice_or_company_search(df, "บริษัท ตัวอย่าง จำกัด")
    assert strict_company is not None
    assert strict_company["Invoice_Number"].tolist() == ["INV001"]

    assert index.strict_invoice_or_company_search(df, "INV").empty
    assert index.strict_invoice_or_company_search(df, "ตัวอย่าง").empty
    assert index.search_dataframe(df, "").empty

    no_helper_df = df.drop(columns=["Invoice_Number_Upper"])
    assert index.strict_invoice_or_company_search(no_helper_df, "inv002")["ชื่อผู้รับเงิน"].tolist() == ["ห้างหุ้นส่วน ทดสอบ"]

    legacy_partial = index.legacy_partial_search(df, "ตัวอย่าง")
    assert legacy_partial is not None
    assert legacy_partial["Invoice_Number"].tolist() == ["INV001"]

    assert index.SEARCH_MODE == "strict"
    assert index.search_dataframe(df, "ตัวอย่าง").empty
