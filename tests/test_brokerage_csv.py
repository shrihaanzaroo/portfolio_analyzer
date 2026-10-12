import pytest

import brokerage_csv

# A small positions export laid out like Fidelity's: money market (SPAXX**), pending activity,
# a Treasury note listed by CUSIP, and a disclaimer after a blank line.
FIDELITY = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar
Z12345678,Individual,SPAXX**,HELD IN MONEY MARKET,,,,"$1,234.56",
Z12345678,Individual,AAPL,APPLE INC,10,$190.00,+$1.00,"$1,900.00",+$10.00
Z12345678,Individual,FXAIX,FIDELITY 500 INDEX FUND,5.123,$180.00,,$922.14,
Z12345678,Individual,Pending Activity,,,,,-$50.00,
Z12345678,Individual,912828XX1,US TREASURY NOTE,1000,,,$990.00,

"The data and information in this spreadsheet is provided to you solely for your use."
"""

# A small positions export laid out like Schwab's: a title line, a blank line, then the table,
# with a cash line and an account total at the bottom.
SCHWAB = """"Positions for account Individual ...123 as of 10:00 AM ET, 2026/10/09","","","","","",""
""
"Symbol","Description","Quantity","Price","Price Change $","Market Value","Day Change $"
"MSFT","MICROSOFT CORP","12","$420.00","$1.00","$5,040.00","$12.00"
"VTI","VANGUARD TOTAL STOCK MARKET ETF","8.5","$280.00","$0.50","$2,380.00","$4.25"
"BRK.B","BERKSHIRE HATHAWAY INC CLASS B","2","$450.00","","$900.00",""
"Cash & Cash Investments","--","--","--","--","$2,500.00","--"
"Account Total","--","--","--","--","$10,820.00","--"
"""


def test_fidelity_shares():
    """Stocks and funds come out with their share counts; cash and the CUSIP line don't."""
    assert brokerage_csv.parse(FIDELITY)["shares"] == {"AAPL": 10.0, "FXAIX": 5.123}


def test_fidelity_cash_includes_money_market_and_pending():
    """The money market fund and pending activity add up into cash."""
    assert brokerage_csv.parse(FIDELITY)["cash"] == 1184.56


def test_fidelity_skips_the_cusip_line():
    """A bond listed by CUSIP number is skipped and mentioned in the notes."""
    result = brokerage_csv.parse(FIDELITY)
    assert result["skipped"] == ["912828XX1"]
    assert any(note.startswith("Skipped 1 line(s)") for note in result["notes"])


def test_schwab_shares():
    """The title line is skipped and every position is read."""
    result = brokerage_csv.parse(SCHWAB)
    assert result["shares"] == {"MSFT": 12.0, "VTI": 8.5, "BRK.B": 2.0}
    assert result["source"] == "positions export"


def test_schwab_cash_and_total():
    """The cash line becomes cash; the account total is ignored."""
    result = brokerage_csv.parse(SCHWAB)
    assert result["cash"] == 2500.0
    assert result["skipped"] == []


def test_file_bytes_with_a_bom_work():
    """A file uploaded as bytes with a UTF-8 byte-order mark reads the same as text."""
    data = ("﻿" + SCHWAB).encode("utf-8")
    assert brokerage_csv.parse(data)["shares"] == brokerage_csv.parse(SCHWAB)["shares"]


def test_activity_report_adds_buys_and_subtracts_sells():
    """In a list of trades, buys add shares and sells take them away."""
    trades = "Date,Action,Symbol,Quantity,Amount\n01/02/2026,Buy,AAPL,10,-1900\n02/02/2026,Sell,AAPL,4,800\n03/02/2026,Buy,MSFT,3,-1200\n"
    result = brokerage_csv.parse(trades)
    assert result["source"] == "activity report"
    assert result["shares"] == {"AAPL": 6.0, "MSFT": 3.0}


def test_value_only_positions_are_kept_separately():
    """A line with a dollar value but no share count is listed under value_only."""
    result = brokerage_csv.parse("Symbol,Market Value\nAAPL,1900\n")
    assert result["shares"] == {} and result["value_only"] == {"AAPL": 1900.0}


def test_file_without_a_symbol_column_is_rejected():
    """A file with no ticker column gives a clear error."""
    with pytest.raises(ValueError):
        brokerage_csv.parse("Name,Amount\nApple,100\n")
