"""6517A-900-01 Rev. D (May 2003), verified against the supplied 343-page PDF.

Manual verification is separate from hardware/firmware testing. Current-limit
paths follow the explicit full commands on printed page 3-108, not indentation
in Table 3-11. No internal resistive-limit resistance is assumed.
"""

MANUAL_VERIFIED = True
MANUAL_SHA256 = "3c02f1e97a0fd101cbc77a09aae87b1d0ce43e45b9bc46d433e671e8dea78adb"
MANUAL_REVISION = "6517A-900-01 Rev. D, May 2003"
FORMAT = "READ,STAT,UNIT,RNUM,VSO"

# Table 3-15 (3-57/58), 3.24.4-6 (3-143/144): Arm Layer 1 has NO delay.
ONE_SHOT_PROFILE = (
    (":ARM:SOUR IMM", ":ARM:SOUR?", "IMM"),
    (":ARM:COUN 1", ":ARM:COUN?", 1),
    (":ARM:LAY2:SOUR IMM", ":ARM:LAY2:SOUR?", "IMM"),
    (":ARM:LAY2:COUN 1", ":ARM:LAY2:COUN?", 1),
    (":ARM:LAY2:DEL 0", ":ARM:LAY2:DEL?", 0),
    (":TRIG:SOUR IMM", ":TRIG:SOUR?", "IMM"),
    (":TRIG:COUN 1", ":TRIG:COUN?", 1),
    (":TRIG:DEL 0", ":TRIG:DEL?", 0),
)

# Tables 3-4/9/10/14; detailed 3-95..100, 3-139/140.
COMMON_PROFILE = (
    (":ROUT:SCAN:LSEL NONE", ":ROUT:SCAN:LSEL?", "NONE"),
    (":TRAC:FEED:CONT NEV", ":TRAC:FEED:CONT?", "NEV"),
    (":SENS:CURR:REF:STAT OFF", ":SENS:CURR:REF:STAT?", False),
    (":SENS:RES:REF:STAT OFF", ":SENS:RES:REF:STAT?", False),
    (":SENS:RES:IREF OFF", ":SENS:RES:IREF?", False),
    (":CALC:STAT OFF", ":CALC:STAT?", False),
    (":CALC2:STAT OFF", ":CALC2:STAT?", False),
    (":CALC3:LIM1:STAT OFF", ":CALC3:LIM1:STAT?", False),
    (":CALC3:LIM2:STAT OFF", ":CALC3:LIM2:STAT?", False),
    (":SYST:HLC ON", ":SYST:HLC?", True),
)


def function_profile(native: bool):
    root = ":SENS:RES" if native else ":SENS:CURR"
    return (
        (root + ":NPLC:AUTO OFF", root + ":NPLC:AUTO?", False),
        (root + ":AVER:STAT OFF", root + ":AVER:STAT?", False),
        (root + ":MED:STAT OFF", root + ":MED:STAT?", False),
    )
