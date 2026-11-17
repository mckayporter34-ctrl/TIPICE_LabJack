"""Canonical apparatus tags shared by desktop clients and the Pi historian."""

UNIT_OP_MAP = {
    "Catalytic Methanation #1": "CatMeth1",
    "Catalytic Methanation #2": "CatMeth2",
    "Packed Columns": "PC",
    "Shell & Tube Heat Exchanger #1": "STHX1",
    "Shell & Tube Heat Exchanger #2": "STHX2",
    "Shell & Tube Heat Exchanger #3": "STHX3",
    "Air Flow Meters": "Airflow",
    "Non-Newtonian Fluids #1": "NNF1",
    "Non-Newtonian Fluids #2": "NNF2",
}

# Legacy Pi polling names. Existing stored data keeps its original tags.
HISTORIAN_UNIT_OP_MAP = {
    "NNF": UNIT_OP_MAP["Non-Newtonian Fluids #1"],
    "Shell_and_Tube_Heat_Exchanger_1": UNIT_OP_MAP["Shell & Tube Heat Exchanger #1"],
    "Shell_and_Tube_Heat_Exchanger_2": UNIT_OP_MAP["Shell & Tube Heat Exchanger #2"],
    "Shell_and_Tube_Heat_Exchanger_3": UNIT_OP_MAP["Shell & Tube Heat Exchanger #3"],
    "Catalytic_Methanation_1": UNIT_OP_MAP["Catalytic Methanation #1"],
    "Catalytic_Methanation_2": UNIT_OP_MAP["Catalytic Methanation #2"],
    "Packed_Columns": UNIT_OP_MAP["Packed Columns"],
}
