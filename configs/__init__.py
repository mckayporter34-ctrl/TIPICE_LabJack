# configs/__init__.py
# Central registry for all apparatus configurations available in the system.

AVAILABLE_CONFIGS = {
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
    # "pump_cart": {
    #     "title": "Pump Cart",
    #     "subtitle": "Water Pump Cart Setup",
    #     "image": "images/Pumpcart_main.jpg",
    #     "active": True,
    #     "accent": "#2f81f7",  # blue
    #     "units": [
    #         {"name": "Unit #1", "module": "configs.pump_cart"}
    #     ]
    # },
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
    # "catalytic_methanation": {
    #     "title": "Catalytic Methanation",
    #     "subtitle": "LabJack T7 Control Panel",
    #     "image": "images/Catmeth_main.jpg",
    #     "active": True,
    #     "accent": "#2f81f7",  # blue
    #     "units": [
    #         {"name": "Unit #1", "module": "configs.catalytic_methanation_1"},
    #         {"name": "Unit #2", "module": "configs.catalytic_methanation_2"}
    #     ]
    # }
}
