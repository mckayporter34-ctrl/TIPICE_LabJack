# configs/__init__.py
# Central registry for all apparatus configurations available in the system.

AVAILABLE_CONFIGS = {
    "shell_tube_hx": {
        "title": "Shell & Tube Heat Exchangers",
        "subtitle": "Shell & Tube Heat Exchanger Units",
        "image": "images/STHX_main.jpg",
        "active": True,
        "accent": "#2f81f7",  # blue
        "units": [
            {"name": "Unit #1", "module": "configs.shell_tube_hx_1"},
            {"name": "Unit #2", "module": "configs.shell_tube_hx_2"},
            {"name": "Unit #3", "module": "configs.shell_tube_hx_3"}
        ]
    },
    "catalytic_methanation": {
        "title": "Catalytic Methanation",
        "subtitle": "LabJack T7 Control Panel",
        "image": "images/Catmeth_main.jpg",
        "active": True,
        "accent": "#2f81f7",  # blue
        "units": [
            {"name": "Unit #1", "module": "configs.catalytic_methanation_1"},
            {"name": "Unit #2", "module": "configs.catalytic_methanation_2"}
        ]
    },
    "packed_columns": {
        "title": "Packed Column",
        "subtitle": "1 Unit  ·  LabJack T7",
        "image": "images/Packedcol_main_apparatus.jpg",
        "active": True,
        "accent": "#2f81f7",  # blue
        "units": [
            {"name": "Unit #1", "module": "configs.packed_columns"}
        ]
    },
    "nonnewtonian": {
        "development": True,
        "title": "Non-Newtonian Fluids",
        "subtitle": "Flow Measurement and Control",
        "image": "PI diagrams/NonNewtonaion_1_V1.png",
        "active": True,
        "accent": "#2f81f7",
        "units": [
            {"name": "Unit #1", "module": "configs.nonnewtonian_1"},
            {"name": "Unit #2", "module": "configs.nonnewtonian_2"}
        ]
    },
    "airflow": {
        "development": True,
        "title": "Air Flow Meters",
        "subtitle": "Airflow Measurement and Control",
        "image": "images/Air_Flow_Apparatus.png",
        "active": True,
        "accent": "#2f81f7",
        "units": [
            {"name": "CB217A · Peter", "module": "configs.airflow"}
        ]
    }
}
