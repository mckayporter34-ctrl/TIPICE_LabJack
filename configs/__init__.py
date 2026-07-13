# configs/__init__.py
# Central registry for all apparatus configurations available in the system.

AVAILABLE_CONFIGS = {
    "packed_columns": {
        "module": "configs.packed_columns",
        "title": "Packed Column",
        "subtitle": "1 Unit  ·  LabJack T7",
        "image": "images/packed_column.jpg",
        "active": True,
        "accent": "#2f81f7"  # blue
    },
    "shell_tube_hx_1": {
        "module": "configs.shell_tube_hx_1",
        "title": "Shell & Tube HX #1",
        "subtitle": "Shell & Tube Heat Exchanger #1",
        "image": "images/shell_tube_hx.jpg",
        "active": True,
        "accent": "#e05f2a"  # orange
    },
    "shell_tube_hx_2": {
        "module": "configs.shell_tube_hx_2",
        "title": "Shell & Tube HX #2",
        "subtitle": "Shell & Tube Heat Exchanger #2",
        "image": "images/shell_tube_hx.jpg",
        "active": True,
        "accent": "#e05f2a"  # orange
    },
    "shell_tube_hx_3": {
        "module": "configs.shell_tube_hx_3",
        "title": "Shell & Tube HX #3",
        "subtitle": "Shell & Tube Heat Exchanger #3",
        "image": "images/shell_tube_hx.jpg",
        "active": True,
        "accent": "#e05f2a"  # orange
    },
    "pump_cart": {
        "module": "configs.pump_cart",
        "title": "Pump Cart",
        "subtitle": "Water Pump Cart Setup",
        "image": "images/pump_cart.jpg",
        "active": True,
        "accent": "#3fb950"  # green
    },
    "catalytic_methanation": {
        "module": "catalytic_methanation.config",
        "title": "Catalytic Methanation",
        "subtitle": "LabJack T7 Control Panel",
        "image": "images/catalytic_methanation.jpg",
        "active": True,
        "accent": "#ea4aaa"  # pink-red accent
    }
}
