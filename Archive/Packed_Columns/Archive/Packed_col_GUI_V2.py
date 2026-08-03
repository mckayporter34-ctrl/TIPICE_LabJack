import tkinter as tk
from tkinter import ttk
from labjack import ljm
import csv
import os
import time
from datetime import datetime
from threading import Thread, Event


class PackedColumnsGuiApp:
    BASE_WIDTH = 1600
    BASE_HEIGHT = 900

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("1350x900")
        self.root.title("Packed Columns")
        self.root.option_add("*tearOff", False)

        self.handle = None
        self.is_logging = False
        self.stop_event = Event()

        self._create_control_variables()
        self._configure_root()
        self._load_themes()
        self._build_ui()
        self._set_initial_states()
        self._schedule_periodic_updates()

        self.root.mainloop()

    def _create_control_variables(self):
        self.a = tk.IntVar()
        self.b = tk.BooleanVar(value=True)
        self.c = tk.BooleanVar()

        self.e = tk.StringVar(value="Connect to Labjack")
        self.f = tk.BooleanVar()
        self.g = tk.DoubleVar(value=0.0)
        self.g1 = tk.DoubleVar(value=0.0)
        self.g2 = tk.DoubleVar(value=0.0)
        self.h = tk.BooleanVar()
        self.rounded_g = tk.IntVar()
        self.rounded_g1 = tk.IntVar()
        self.rounded_g2 = tk.IntVar()

        self.air_flowrate_setpoint_var = tk.StringVar(value='0')
        self.air_flowrate_input = "AIN0"
        self.air_flowrate_var = tk.StringVar()

        self.co2_concentration_input = ""
        self.co2_concentration_var = tk.StringVar()

        self.water_flowrate_setpoint_var = tk.StringVar(value='0')
        self.water_flowrate_input = "AIN1"
        self.water_flowrate_output = "DAC1"
        self.water_flowrate_var = tk.StringVar()

        self.water_temperature_input = "AIN6"
        self.water_temperature_var = tk.StringVar()

        self.column1_pressure_drop_input = "AIN2"
        self.column1_pressure_drop_var = tk.StringVar()

        self.column2_pressure_drop_input = "AIN3"
        self.column2_pressure_drop_var = tk.StringVar()

        self.column1_level_input = "AIN4"
        self.column1_level_setpoint_var = tk.StringVar(value='0')
        self.column1_level_var = tk.StringVar()

        self.column2_level_input = "AIN5"
        self.column2_level_setpoint_var = tk.StringVar(value='0')
        self.column2_level_var = tk.StringVar()

        self.column1_level_output = "DAC0"
        self.column2_level_output = "DAC0"
        self.air_setpoint_output = "TDAC0"

        self.main_power_output = "FIO6"
        self.column_selector_output = "FIO7"

        self.logging_text_var = tk.StringVar(value='Start Logging')
        self.time_between_data_var = tk.DoubleVar(value=1.0)
        self.data_point_count_var = tk.IntVar(value=0)

        self.water_Kc = tk.DoubleVar(value=0.14)
        self.column1_Kc = tk.DoubleVar(value=-0.05)
        self.column2_Kc = tk.DoubleVar(value=-0.05)
        self.water_Ti = tk.DoubleVar(value=0.06)
        self.column1_Ti = tk.DoubleVar(value=2.0)
        self.column2_Ti = tk.DoubleVar(value=2.0)
        self.water_Td = tk.DoubleVar(value=0.0)
        self.column1_Td = tk.DoubleVar(value=0.0)
        self.column2_Td = tk.DoubleVar(value=0.0)

        self.main_power_boolean = False
        self.water_manual_override_boolean = False
        self.column1_manual_override_boolean = False
        self.column2_manual_override_boolean = False
        self.column_selector_boolean = tk.BooleanVar(value=True)

        self.main_power_ui_var = tk.BooleanVar(value=False)
        self.water_manual_ui_var = tk.BooleanVar(value=False)
        self.column1_manual_ui_var = tk.BooleanVar(value=False)
        self.column2_manual_ui_var = tk.BooleanVar(value=False)

        self.connection_menu_list = ["USB", "Ethernet", "Disconnect"]

    def _configure_root(self):
        self.root.columnconfigure(index=0, weight=1)
        self.root.columnconfigure(index=1, weight=1)
        self.root.columnconfigure(index=2, weight=1)
        self.root.rowconfigure(index=0, weight=1)
        self.root.rowconfigure(index=1, weight=1)
        self.root.rowconfigure(index=2, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        scalef = min(screen_w / self.BASE_WIDTH, screen_h / self.BASE_HEIGHT)
        self.root.tk.eval(f"set scalef {scalef:.3f}")
        self.root.tk.call('source', 'forest-dark.tcl')
        self.root.tk.call('source', 'forest-light.tcl')

    def _load_themes(self):
        self.style = ttk.Style()
        self.style.theme_use('forest-light')
        self.style.configure("Green.TLabel", foreground="green")
        self.style.configure("Red.TLabel", foreground="red")

    def _build_ui(self):
        self.container = ttk.Frame(self.root)
        self.container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.container)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = ttk.Scrollbar(self.container, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollable_frame.bind("<Configure>", self.on_frame_configure)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", self._on_mousewheel))
        self.scrollable_frame.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        self._create_control_frame()
        self._create_air_flow_frame()
        self._create_data_logging_frame()
        self._create_separator()
        self._create_logo_frame()
        self._create_water_frame()
        self._create_column1_frame()
        self._create_column2_frame()

    def _create_control_frame(self):
        self.control_frame = ttk.LabelFrame(self.scrollable_frame, text="Controls", padding=(20, 10))
        self.control_frame.grid(row=0, column=0, padx=(20, 10), pady=(10, 10), sticky="nsew")

        self.connect_dropdown = ttk.OptionMenu(
            self.control_frame,
            self.e,
            "Connect to Labjack",
            *self.connection_menu_list,
            command=self.connect_to_labjack,
        )
        self.connect_dropdown.grid(row=0, column=0, padx=5, pady=(10, 5), sticky="nsew")

        self.connection_status = ttk.Label(self.control_frame, text="Connection Status", padding=(5, 5))
        self.connection_status.grid(row=1, column=0, padx=5, pady=0, sticky="nsew")

        self.power_switch = ttk.Checkbutton(
            self.control_frame,
            text="Main Power: OFF",
            style="Switch",
            variable=self.main_power_ui_var,
            command=self.main_power,
        )
        self.power_switch.grid(row=2, column=0, padx=5, pady=10, sticky="nsew")

        self.column1_selector = ttk.Radiobutton(
            self.control_frame,
            text="Column 1 (White)",
            variable=self.column_selector_boolean,
            value=True,
        )
        self.column1_selector.grid(row=4, column=0, padx=5, pady=10, sticky="nsew")

        self.column2_selector = ttk.Radiobutton(
            self.control_frame,
            text="Column 2 (Blue)",
            variable=self.column_selector_boolean,
            value=False,
        )
        self.column2_selector.grid(row=5, column=0, padx=5, pady=(5, 5), sticky="nsew")

        self.column_selector_boolean.trace_add('write', self.update_column_selector)

    def _create_air_flow_frame(self):
        self.air_flow_frame = ttk.LabelFrame(self.scrollable_frame, text="Air Flow", padding=(20, 10))
        self.air_flow_frame.grid(row=0, column=1, padx=(20, 10), pady=(10, 10), sticky="nsew")

        self.air_flow_setpoint_label = ttk.Label(self.air_flow_frame, text="Air Flow Setpoint (SLPM)")
        self.air_flow_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="nsew")

        self.air_flow_setpoint_spinbox = ttk.Spinbox(
            self.air_flow_frame,
            from_=0,
            to=1000,
            textvariable=self.air_flowrate_setpoint_var,
            width=5,
            state="disabled",
        )
        self.air_flow_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5, 10), sticky="nsew")

        self.air_flow_label = ttk.Label(self.air_flow_frame, text="Air Flow (SLPM)")
        self.air_flow_label.grid(row=2, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.air_flow_entry = ttk.Entry(
            self.air_flow_frame,
            width=10,
            textvariable=self.air_flowrate_var,
            state="readonly",
        )
        self.air_flow_entry.grid(row=3, column=0, padx=5, pady=(5, 10), sticky="nsew")

        self.co2_concentration_label = ttk.Label(
            self.air_flow_frame,
            text="Delta CO2 Concentration (ppm)",
        )
        self.co2_concentration_label.grid(row=4, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.co2_concentration_entry = ttk.Entry(
            self.air_flow_frame,
            width=10,
            textvariable=self.co2_concentration_var,
            state="readonly",
        )
        self.co2_concentration_entry.grid(row=5, column=0, padx=5, pady=(5, 10), sticky="nsew")

    def _create_data_logging_frame(self):
        self.data_logging_frame = ttk.LabelFrame(self.scrollable_frame, text="Data Logging", padding=(20, 10))
        self.data_logging_frame.grid(row=1, column=0, columnspan=2, padx=(20, 10), pady=(10, 10), sticky="nsew")

        self.time_between_data_label = ttk.Label(self.data_logging_frame, text="Time Between Data")
        self.time_between_data_label.grid(row=0, column=1, padx=5, pady=(20, 5), sticky="nsew")

        self.time_between_data_spinbox = ttk.Spinbox(
            self.data_logging_frame,
            from_=0,
            to=100,
            textvariable=self.time_between_data_var,
            width=5,
            state="normal",
        )
        self.time_between_data_spinbox.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        self.data_point_count_label = ttk.Label(self.data_logging_frame, text="Data Point Count")
        self.data_point_count_label.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

        self.data_point_count_entry = ttk.Entry(
            self.data_logging_frame,
            textvariable=self.data_point_count_var,
            state="disabled",
        )
        self.data_point_count_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

        self.toggle_logging_button = ttk.Checkbutton(
            self.data_logging_frame,
            textvariable=self.logging_text_var,
            style="ToggleButton",
            command=self.toggle_logging,
            padding=(20, 20),
        )
        self.toggle_logging_button.grid(row=0, rowspan=4, column=0, padx=40, pady=(20, 5), sticky="nsew")

    def _create_separator(self):
        self.separator = ttk.Separator(self.scrollable_frame)
        self.separator.grid(row=0, column=2, rowspan=3, padx=(20, 10), pady=10, sticky="ns")

    def _create_logo_frame(self):
        self.logo_frame = tk.LabelFrame(self.scrollable_frame, borderwidth=0, relief="flat")
        self.logo_frame.grid(row=2, column=0, columnspan=2, padx=(40, 10), pady=(0, 0), sticky="nsew")

        self.img = tk.PhotoImage(file="tipice_logo.png")
        self.logo = ttk.Label(self.logo_frame, image=self.img)
        self.logo.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.logo_label = ttk.Label(
            self.logo_frame,
            text="BYU TIPICE",
            font=("Copperplate Gothic Bold", 60),
            wraplength=300,
        )
        self.logo_label.grid(row=0, column=1, padx=(5, 20), pady=5, sticky="nsew")

        self.light_or_dark = ttk.Checkbutton(
            self.logo_frame,
            text="Dark Mode",
            style="ToggleButton",
            command=self.light_or_dark_mode,
        )
        self.light_or_dark.grid(row=1, column=0, columnspan=2, padx=5, pady=10)

    def _create_water_frame(self):
        self.water_frame = ttk.LabelFrame(self.scrollable_frame, text="Water", padding=(20, 10))
        self.water_frame.grid(row=0, column=3, columnspan=3, padx=(20, 20), pady=(10, 10), sticky="nsew")

        self.water_flow_setpoint_label = ttk.Label(
            self.water_frame,
            text="Water Flowrate Setpoint (l/min)",
        )
        self.water_flow_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")

        self.water_flow_setpoint_spinbox = ttk.Spinbox(
            self.water_frame,
            from_=0,
            to=50,
            textvariable=self.water_flowrate_setpoint_var,
            width=5,
            state="disabled",
        )
        self.water_flow_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.water_flowrate_label = ttk.Label(self.water_frame, text="Water Flowrate (l/min)")
        self.water_flowrate_label.grid(row=2, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.water_flowrate_entry = ttk.Entry(
            self.water_frame,
            textvariable=self.water_flowrate_var,
            state="disabled",
            width=10,
        )
        self.water_flowrate_entry.grid(row=3, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.water_temperature_label = ttk.Label(self.water_frame, text="Water Temp (C)")
        self.water_temperature_label.grid(row=4, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.water_temperature_entry = ttk.Entry(
            self.water_frame,
            textvariable=self.water_temperature_var,
            state="readonly",
            width=10,
        )
        self.water_temperature_entry.grid(row=5, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.water_override_label = ttk.Label(
            self.water_frame,
            width=20,
            text="Manual Override",
        )
        self.water_override_label.grid(row=0, column=1, columnspan=3, padx=(40, 0), pady=0, sticky="nsew")

        self.water_manual_switch = ttk.Checkbutton(
            self.water_frame,
            text="Mode: Manual",
            style="Switch",
            variable=self.water_manual_ui_var,
            command=self.water_manual_override_button,
        )
        self.water_manual_switch.grid(row=1, column=1, columnspan=3, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.water_set_manual_label = ttk.Label(
            self.water_frame,
            text="Set Manual Valve Output",
        )
        self.water_set_manual_label.grid(row=2, column=1, columnspan=4, padx=(40, 0), pady=(10, 0), sticky="nsew")

        self.water_scale = ttk.Scale(
            self.water_frame,
            from_=0,
            to=100,
            variable=self.g,
        )
        self.water_scale.grid(row=3, column=1, columnspan=3, padx=(40, 5), pady=(5, 0), sticky="ew")

        self.water_manual_override_spinbox = ttk.Spinbox(
            self.water_frame,
            from_=0,
            to=100,
            width=3,
            textvariable=self.rounded_g,
            state="normal",
        )
        self.water_manual_override_spinbox.grid(row=3, column=4, padx=5, pady=(5, 10), sticky="ew")
        self.water_manual_override_spinbox.bind("<Return>", self._commit_water_manual)
        self.water_manual_override_spinbox.bind("<FocusOut>", self._commit_water_manual)

        self.g.trace_add("write", self._update_water_spinbox_from_scale)
        self.water_manual_override_spinbox.set(round(self.g.get()))

        self.water_scale_label_0 = ttk.Label(self.water_frame, text="0", anchor='w')
        self.water_scale_label_0.grid(row=4, column=1, padx=(40, 0), pady=0, sticky="ew")
        self.water_scale_label_50 = ttk.Label(self.water_frame, text="   50", anchor='center')
        self.water_scale_label_50.grid(row=4, column=2, padx=0, pady=0, sticky="ew")
        self.water_scale_label_100 = ttk.Label(self.water_frame, text="100", anchor='e')
        self.water_scale_label_100.grid(row=4, column=3, padx=0, pady=0, sticky="ew")

        self.water_flow_valve_output_frame = tk.LabelFrame(
            self.water_frame,
            borderwidth=0,
            relief="flat",
        )
        self.water_flow_valve_output_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=(0, 0), sticky="nsew")

        self.water_flow_valve_output_label = ttk.Label(
            self.water_flow_valve_output_frame,
            text="Flow Valve Output (%)",
        )
        self.water_flow_valve_output_label.grid(row=0, column=0, columnspan=3, padx=0, pady=0, sticky="nsew")
        self.water_flow_valve_output_label.grid_propagate(False)

        self.water_progress_label_0 = ttk.Label(
            self.water_flow_valve_output_frame,
            text="100",
            anchor='ne',
        )
        self.water_progress_label_0.grid(row=1, column=0, padx=(0, 0), pady=0, sticky="ew")

        self.water_progress_label_50 = ttk.Label(self.water_flow_valve_output_frame, text="50")
        self.water_progress_label_50.grid(row=2, column=0, padx=0, pady=(10, 0), sticky="e")

        self.water_progress_label_100 = ttk.Label(
            self.water_flow_valve_output_frame,
            text="0",
            anchor='se',
        )
        self.water_progress_label_100.grid(row=3, column=0, padx=0, pady=0, sticky="se")

        self.progress = ttk.Progressbar(
            self.water_flow_valve_output_frame,
            orient="vertical",
            value=0,
            variable=self.g,
            mode="determinate",
        )
        self.progress.grid(row=1, rowspan=3, column=1, padx=(0, 0), pady=(10, 0), sticky="ns")

        self.water_flow_valve_entry = ttk.Entry(
            self.water_flow_valve_output_frame,
            state="readonly",
            textvariable=self.rounded_g,
            width=5,
        )
        self.water_flow_valve_entry.grid(row=1, column=2, padx=(5, 0), pady=0, sticky="ew")

        self.water_Kp_label = ttk.Label(self.water_frame, text="Kc")
        self.water_Kp_label.grid(row=0, column=6, columnspan=2, padx=40, pady=0, sticky="nsew")

        self.water_Kp_spinbox = ttk.Spinbox(
            self.water_frame,
            textvariable=self.water_Kc,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.water_Kp_spinbox.grid(row=1, column=6, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.water_Ti_label = ttk.Label(self.water_frame, text="Ti")
        self.water_Ti_label.grid(row=2, column=6, columnspan=2, padx=40, pady=(10, 0), sticky="nsew")

        self.water_Ti_spinbox = ttk.Spinbox(
            self.water_frame,
            textvariable=self.water_Ti,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.water_Ti_spinbox.grid(row=3, column=6, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.water_Ti_units_label = ttk.Label(self.water_frame, text="(min)")
        self.water_Ti_units_label.grid(row=3, column=7, padx=(5, 0), pady=(5, 10), sticky="nsew")

        self.water_Td_label = ttk.Label(self.water_frame, text="Td")
        self.water_Td_label.grid(row=4, column=6, columnspan=2, padx=40, pady=(10, 0), sticky="nsew")

        self.water_Td_spinbox = ttk.Spinbox(
            self.water_frame,
            textvariable=self.water_Td,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.water_Td_spinbox.grid(row=5, column=6, padx=(40, 0), pady=(5, 10), sticky="nsew")

        self.water_Td_units_label = ttk.Label(self.water_frame, text="(min)")
        self.water_Td_units_label.grid(row=5, column=7, padx=(5, 0), pady=(5, 10), sticky="nsew")

    def _create_column1_frame(self):
        self.column1_frame = ttk.LabelFrame(self.scrollable_frame, text="Column 1", padding=(20, 10))
        self.column1_frame.grid(row=1, column=3, columnspan=3, padx=(20, 20), pady=(10, 10), sticky="nsew")

        self.column1_level_setpoint_label = ttk.Label(
            self.column1_frame,
            text="Column 1 Level Setpoint (mm)",
        )
        self.column1_level_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")

        self.column1_level_setpoint_spinbox = ttk.Spinbox(
            self.column1_frame,
            from_=0,
            to=100,
            textvariable=self.column1_level_setpoint_var,
            width=5,
            state="disabled",
        )
        self.column1_level_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.column1_level_label = ttk.Label(self.column1_frame, text="Column 1 Level (mm)")
        self.column1_level_label.grid(row=2, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.column1_level_entry = ttk.Entry(
            self.column1_frame,
            textvariable=self.column1_level_var,
            state="readonly",
            width=10,
        )
        self.column1_level_entry.grid(row=3, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.column1_delta_p_label = ttk.Label(
            self.column1_frame,
            text="Column 1 Pressure Drop (Pa)",
        )
        self.column1_delta_p_label.grid(row=4, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.column1_delta_p_entry = ttk.Entry(
            self.column1_frame,
            textvariable=self.column1_pressure_drop_var,
            width=10,
        )
        self.column1_delta_p_entry.grid(row=5, column=0, padx=5, pady=(5, 10), sticky="nsew")

        self.column1_override_label = ttk.Label(
            self.column1_frame,
            width=20,
            text="Manual Override",
        )
        self.column1_override_label.grid(row=0, column=1, columnspan=3, padx=(40, 0), pady=0, sticky="nsew")

        self.column1_manual_switch = ttk.Checkbutton(
            self.column1_frame,
            text="Mode: Manual",
            style="Switch",
            variable=self.column1_manual_ui_var,
            command=self.column1_manual_override_button,
        )
        self.column1_manual_switch.grid(row=1, column=1, columnspan=3, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.column1_set_manual_label = ttk.Label(
            self.column1_frame,
            text="Set Manual Valve Output",
        )
        self.column1_set_manual_label.grid(row=2, column=1, columnspan=4, padx=(40, 0), pady=(10, 0), sticky="nsew")

        self.column1_scale = ttk.Scale(
            self.column1_frame,
            from_=0,
            to=100,
            variable=self.g1,
        )
        self.column1_scale.grid(row=3, column=1, columnspan=3, padx=(40, 5), pady=(5, 0), sticky="ew")

        self.column1_manual_override_spinbox = ttk.Spinbox(
            self.column1_frame,
            from_=0,
            to=100,
            width=3,
            textvariable=self.rounded_g1,
            state="normal",
        )
        self.column1_manual_override_spinbox.grid(row=3, column=4, padx=5, pady=(5, 10), sticky="ew")
        self.column1_manual_override_spinbox.bind("<Return>", self._commit_column1_manual)
        self.column1_manual_override_spinbox.bind("<FocusOut>", self._commit_column1_manual)

        self.g1.trace_add("write", self._update_column1_spinbox_from_scale)
        self.column1_manual_override_spinbox.set(round(self.g1.get()))

        self.column1_scale_label_0 = ttk.Label(self.column1_frame, text="0", anchor='w')
        self.column1_scale_label_0.grid(row=4, column=1, padx=(40, 0), pady=0, sticky="ew")
        self.column1_scale_label_50 = ttk.Label(self.column1_frame, text="   50", anchor='center')
        self.column1_scale_label_50.grid(row=4, column=2, padx=0, pady=0, sticky="ew")
        self.column1_scale_label_100 = ttk.Label(self.column1_frame, text="100", anchor='e')
        self.column1_scale_label_100.grid(row=4, column=3, padx=0, pady=0, sticky="ew")

        self.column1_level_valve_output_frame = tk.LabelFrame(
            self.column1_frame,
            borderwidth=0,
            relief="flat",
        )
        self.column1_level_valve_output_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=(0, 0), sticky="nsew")

        self.column1_level_valve_output_label = ttk.Label(
            self.column1_level_valve_output_frame,
            text="Flow Valve Output (%)",
        )
        self.column1_level_valve_output_label.grid(row=0, column=0, columnspan=3, padx=0, pady=0, sticky="nsew")
        self.column1_level_valve_output_label.grid_propagate(False)

        self.column1_progress_label_0 = ttk.Label(
            self.column1_level_valve_output_frame,
            text="100",
            anchor='ne',
        )
        self.column1_progress_label_0.grid(row=1, column=0, padx=(0, 0), pady=0, sticky="ew")

        self.column1_progress_label_50 = ttk.Label(self.column1_level_valve_output_frame, text="50")
        self.column1_progress_label_50.grid(row=2, column=0, padx=0, pady=(10, 0), sticky="e")

        self.column1_progress_label_100 = ttk.Label(
            self.column1_level_valve_output_frame,
            text="0",
            anchor='se',
        )
        self.column1_progress_label_100.grid(row=3, column=0, padx=0, pady=0, sticky="se")

        self.column1_progress = ttk.Progressbar(
            self.column1_level_valve_output_frame,
            orient="vertical",
            value=0,
            variable=self.g1,
            mode="determinate",
        )
        self.column1_progress.grid(row=1, rowspan=3, column=1, padx=(0, 0), pady=(10, 0), sticky="ns")

        self.column1_level_valve_entry = ttk.Entry(
            self.column1_level_valve_output_frame,
            state="readonly",
            textvariable=self.rounded_g1,
            width=5,
        )
        self.column1_level_valve_entry.grid(row=1, column=2, padx=(5, 0), pady=0, sticky="ew")

        self.column1_Kc_label = ttk.Label(self.column1_frame, text="Kc")
        self.column1_Kc_label.grid(row=0, column=6, columnspan=2, padx=40, pady=0, sticky="nsew")

        self.column1_Kc_spinbox = ttk.Spinbox(
            self.column1_frame,
            textvariable=self.column1_Kc,
            from_=-100,
            to=100,
            width=5,
            state="disabled",
        )
        self.column1_Kc_spinbox.grid(row=1, column=6, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.column1_Ti_label = ttk.Label(self.column1_frame, text="Ti")
        self.column1_Ti_label.grid(row=2, column=6, columnspan=2, padx=40, pady=(10, 0), sticky="nsew")

        self.column1_Ti_spinbox = ttk.Spinbox(
            self.column1_frame,
            textvariable=self.column1_Ti,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.column1_Ti_spinbox.grid(row=3, column=6, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.column1_Ti_units_label = ttk.Label(self.column1_frame, text="(min)")
        self.column1_Ti_units_label.grid(row=3, column=7, padx=(5, 0), pady=(5, 10), sticky="nsew")

        self.column1_Td_label = ttk.Label(self.column1_frame, text="Td")
        self.column1_Td_label.grid(row=4, column=6, columnspan=2, padx=40, pady=(10, 0), sticky="nsew")

        self.column1_Td_spinbox = ttk.Spinbox(
            self.column1_frame,
            textvariable=self.column1_Td,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.column1_Td_spinbox.grid(row=5, column=6, padx=(40, 0), pady=(5, 10), sticky="nsew")

        self.column1_Td_units_label = ttk.Label(self.column1_frame, text="(min)")
        self.column1_Td_units_label.grid(row=5, column=7, padx=(5, 0), pady=(5, 10), sticky="nsew")

    def _create_column2_frame(self):
        self.column2_frame = ttk.LabelFrame(self.scrollable_frame, text="Column 2", padding=(20, 10))
        self.column2_frame.grid(row=2, column=3, columnspan=3, padx=(20, 20), pady=(10, 10), sticky="nsew")

        self.column2_level_setpoint_label = ttk.Label(
            self.column2_frame,
            text="Column 2 Level Setpoint (mm)",
        )
        self.column2_level_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")

        self.column2_level_setpoint_spinbox = ttk.Spinbox(
            self.column2_frame,
            from_=0,
            to=100,
            textvariable=self.column2_level_setpoint_var,
            width=5,
            state="disabled",
        )
        self.column2_level_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.column2_level_label = ttk.Label(self.column2_frame, text="Column 2 Level (mm)")
        self.column2_level_label.grid(row=2, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.column2_level_entry = ttk.Entry(
            self.column2_frame,
            textvariable=self.column2_level_var,
            state="readonly",
            width=10,
        )
        self.column2_level_entry.grid(row=3, column=0, padx=5, pady=(5, 10), sticky="ew")

        self.column2_delta_p_label = ttk.Label(
            self.column2_frame,
            text="Column 2 Pressure Drop (Pa)",
        )
        self.column2_delta_p_label.grid(row=4, column=0, padx=5, pady=(10, 0), sticky="nsew")

        self.column2_delta_p_entry = ttk.Entry(
            self.column2_frame,
            textvariable=self.column2_pressure_drop_var,
            width=10,
        )
        self.column2_delta_p_entry.grid(row=5, column=0, padx=5, pady=(5, 10), sticky="nsew")

        self.column2_override_label = ttk.Label(
            self.column2_frame,
            width=20,
            text="Manual Override",
        )
        self.column2_override_label.grid(row=0, column=1, columnspan=3, padx=(40, 0), pady=0, sticky="nsew")

        self.column2_manual_switch = ttk.Checkbutton(
            self.column2_frame,
            text="Mode: Manual",
            style="Switch",
            variable=self.column2_manual_ui_var,
            command=self.column2_manual_override_button,
        )
        self.column2_manual_switch.grid(row=1, column=1, columnspan=3, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.column2_set_manual_label = ttk.Label(
            self.column2_frame,
            text="Set Manual Valve Output",
        )
        self.column2_set_manual_label.grid(row=2, column=1, columnspan=4, padx=(40, 0), pady=(10, 0), sticky="nsew")

        self.column2_scale = ttk.Scale(
            self.column2_frame,
            from_=0,
            to=100,
            variable=self.g2,
        )
        self.column2_scale.grid(row=3, column=1, columnspan=3, padx=(40, 5), pady=(5, 0), sticky="ew")

        self.column2_manual_override_spinbox = ttk.Spinbox(
            self.column2_frame,
            from_=0,
            to=100,
            width=3,
            textvariable=self.rounded_g2,
            state="normal",
        )
        self.column2_manual_override_spinbox.grid(row=3, column=4, padx=5, pady=(5, 10), sticky="ew")
        self.column2_manual_override_spinbox.bind("<Return>", self._commit_column2_manual)
        self.column2_manual_override_spinbox.bind("<FocusOut>", self._commit_column2_manual)

        self.g2.trace_add("write", self._update_column2_spinbox_from_scale)
        self.column2_manual_override_spinbox.set(round(self.g2.get()))

        self.column2_scale_label_0 = ttk.Label(self.column2_frame, text="0", anchor='w')
        self.column2_scale_label_0.grid(row=4, column=1, padx=(40, 0), pady=0, sticky="ew")
        self.column2_scale_label_50 = ttk.Label(self.column2_frame, text="   50", anchor='center')
        self.column2_scale_label_50.grid(row=4, column=2, padx=0, pady=0, sticky="ew")
        self.column2_scale_label_100 = ttk.Label(self.column2_frame, text="100", anchor='e')
        self.column2_scale_label_100.grid(row=4, column=3, padx=0, pady=0, sticky="ew")

        self.column2_level_valve_output_frame = tk.LabelFrame(
            self.column2_frame,
            borderwidth=0,
            relief="flat",
        )
        self.column2_level_valve_output_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=(0, 0), sticky="nsew")

        self.column2_level_valve_output_label = ttk.Label(
            self.column2_level_valve_output_frame,
            text="Flow Valve Output (%)",
        )
        self.column2_level_valve_output_label.grid(row=0, column=0, columnspan=3, padx=0, pady=0, sticky="nsew")
        self.column2_level_valve_output_label.grid_propagate(False)

        self.column2_progress_label_0 = ttk.Label(
            self.column2_level_valve_output_frame,
            text="100",
            anchor='ne',
        )
        self.column2_progress_label_0.grid(row=1, column=0, padx=(0, 0), pady=0, sticky="ew")

        self.column2_progress_label_50 = ttk.Label(self.column2_level_valve_output_frame, text="50")
        self.column2_progress_label_50.grid(row=2, column=0, padx=0, pady=(10, 0), sticky="e")

        self.column2_progress_label_100 = ttk.Label(
            self.column2_level_valve_output_frame,
            text="0",
            anchor='se',
        )
        self.column2_progress_label_100.grid(row=3, column=0, padx=0, pady=0, sticky="se")

        self.column2_progress = ttk.Progressbar(
            self.column2_level_valve_output_frame,
            orient="vertical",
            value=0,
            variable=self.g2,
            mode="determinate",
        )
        self.column2_progress.grid(row=1, rowspan=3, column=1, padx=(0, 0), pady=(10, 0), sticky="ns")

        self.column2_level_valve_entry = ttk.Entry(
            self.column2_level_valve_output_frame,
            state="readonly",
            textvariable=self.rounded_g2,
            width=5,
        )
        self.column2_level_valve_entry.grid(row=1, column=2, padx=(5, 0), pady=0, sticky="ew")

        self.column2_Kc_label = ttk.Label(self.column2_frame, text="Kc")
        self.column2_Kc_label.grid(row=0, column=6, columnspan=2, padx=40, pady=0, sticky="nsew")

        self.column2_Kc_spinbox = ttk.Spinbox(
            self.column2_frame,
            textvariable=self.column2_Kc,
            from_=-100,
            to=100,
            width=5,
            state="disabled",
        )
        self.column2_Kc_spinbox.grid(row=1, column=6, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.column2_Ti_label = ttk.Label(self.column2_frame, text="Ti")
        self.column2_Ti_label.grid(row=2, column=6, columnspan=2, padx=40, pady=(10, 0), sticky="nsew")

        self.column2_Ti_spinbox = ttk.Spinbox(
            self.column2_frame,
            textvariable=self.column2_Ti,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.column2_Ti_spinbox.grid(row=3, column=6, padx=(40, 0), pady=(5, 10), sticky="ew")

        self.column2_Ti_units_label = ttk.Label(self.column2_frame, text="(min)")
        self.column2_Ti_units_label.grid(row=3, column=7, padx=(5, 0), pady=(5, 10), sticky="nsew")

        self.column2_Td_label = ttk.Label(self.column2_frame, text="Td")
        self.column2_Td_label.grid(row=4, column=6, columnspan=2, padx=40, pady=(10, 0), sticky="nsew")

        self.column2_Td_spinbox = ttk.Spinbox(
            self.column2_frame,
            textvariable=self.column2_Td,
            from_=0,
            to=100,
            width=5,
            state="disabled",
        )
        self.column2_Td_spinbox.grid(row=5, column=6, padx=(40, 0), pady=(5, 10), sticky="nsew")

        self.column2_Td_units_label = ttk.Label(self.column2_frame, text="(min)")
        self.column2_Td_units_label.grid(row=5, column=7, padx=(5, 0), pady=(5, 10), sticky="nsew")

    def _set_initial_states(self):
        self.power_switch.configure(state='disabled')
        self.toggle_logging_button.configure(state='disabled')
        self.air_flow_setpoint_spinbox.configure(state='disabled')
        self.air_flow_entry.configure(state='disabled')
        self.co2_concentration_entry.configure(state='disabled')
        self.water_flow_setpoint_spinbox.configure(state='disabled')
        self.water_flowrate_entry.configure(state='disabled')
        self.water_temperature_entry.configure(state='disabled')
        self.water_manual_switch.configure(state='disabled')
        self.water_scale.configure(state='disabled')
        self.water_manual_override_spinbox.configure(state='disabled')
        self.water_flow_valve_entry.configure(state='disabled')
        self.water_Kp_spinbox.configure(state='disabled')
        self.water_Ti_spinbox.configure(state='disabled')
        self.water_Td_spinbox.configure(state='disabled')
        self.column1_level_setpoint_spinbox.configure(state='disabled')
        self.column1_level_entry.configure(state='disabled')
        self.column1_delta_p_entry.configure(state='disabled')
        self.column1_manual_switch.configure(state='disabled')
        self.column1_scale.configure(state='disabled')
        self.column1_manual_override_spinbox.configure(state='disabled')
        self.column1_level_valve_entry.configure(state='disabled')
        self.column1_Kc_spinbox.configure(state='disabled')
        self.column1_Ti_spinbox.configure(state='disabled')
        self.column1_Td_spinbox.configure(state='disabled')
        self.column2_level_setpoint_spinbox.configure(state='disabled')
        self.column2_level_entry.configure(state='disabled')
        self.column2_delta_p_entry.configure(state='disabled')
        self.column2_manual_switch.configure(state='disabled')
        self.column2_scale.configure(state='disabled')
        self.column2_manual_override_spinbox.configure(state='disabled')
        self.column2_level_valve_entry.configure(state='disabled')
        self.column2_Kc_spinbox.configure(state='disabled')
        self.column2_Ti_spinbox.configure(state='disabled')
        self.column2_Td_spinbox.configure(state='disabled')

    def _schedule_periodic_updates(self):
        self.root.after(500, self.update_air_flowrate_entry)
        self.root.after(500, self.update_air_flow_output)
        self.root.after(500, self.update_co2_concentration_entry)
        self.root.after(500, self.update_water_flowrate_entry)
        self.root.after(500, self.update_water_temperature_entry)
        self.root.after(500, self.update_column1_level_entry)
        self.root.after(500, self.update_column1_delta_p_entry)
        self.root.after(500, self.update_column2_level_entry)
        self.root.after(500, self.update_column2_delta_p_entry)
        self.root.after(500, self.auto_update_water_control_valve)
        self.root.after(500, self.manual_update_water_control_valve)
        self.root.after(500, self.auto_update_column1_control_valve)
        self.root.after(500, self.manual_update_column1_control_valve)
        self.root.after(500, self.auto_update_column2_control_valve)
        self.root.after(500, self.manual_update_column2_control_valve)

    def _safe_write(self, register, value):
        if self.handle is None:
            return
        ljm.eWriteName(self.handle, register, value)

    def _safe_read(self, register):
        if self.handle is None:
            raise RuntimeError("LabJack not connected")
        return ljm.eReadName(self.handle, register)

    def connect_to_labjack(self, choice):
        if choice == "USB":
            self.connect("T7", "USB", "ANY")
        elif choice == "Ethernet":
            self.connect("T7", "ETHERNET", "10.8.112.59")
        elif choice == "Disconnect":
            self.disconnect()

    def connect(self, t7, connection_type, identifier):
        try:
            self.handle = ljm.openS(t7, connection_type, identifier)
            self.connection_status.config(text="Connected", style="Green.TLabel")
            self._safe_write("I2C_SPEED_THROTTLE", 65536)
            self.power_switch.configure(state='normal')
            self.update_column_selector()
        except Exception as exc:
            self.handle = None
            self.power_switch.configure(state='disabled')
            self.connection_status.config(text=f'Failed to connect: {exc}', style="Red.TLabel")
            print(exc)

    def disconnect(self):
        if self.handle is not None:
            ljm.close(self.handle)
            self.handle = None
            self.connection_status.config(text="LabJack disconnected", style="Green.TLabel")
            self.power_switch.configure(state='disabled')
            self.main_power_boolean = False
            self.main_power_ui_var.set(False)
            self.power_switch.config(text="Main Power: OFF")

    def main_power(self):
        self.main_power_boolean = not self.main_power_boolean
        if self.main_power_boolean:
            self.power_switch.config(text="Main Power: ON")
            self._safe_write(self.main_power_output, 1)
            self._enable_powered_controls()
        else:
            self.power_switch.config(text="Main Power: OFF")
            self._safe_write(self.main_power_output, 0)
            self._disable_powered_controls()

    def _enable_powered_controls(self):
        self.air_flow_setpoint_spinbox.configure(state='normal')
        self.air_flow_entry.configure(state='readonly')
        self.co2_concentration_entry.configure(state='readonly')
        self.water_flow_setpoint_spinbox.configure(state='normal')
        self.water_flowrate_entry.configure(state='readonly')
        self.water_temperature_entry.configure(state='readonly')
        self.water_manual_switch.configure(state='normal')
        self.water_scale.configure(state='normal')
        self.water_manual_override_spinbox.configure(state='normal')
        self.water_flow_valve_entry.configure(state='readonly')
        self.water_Kp_spinbox.configure(state='normal')
        self.water_Ti_spinbox.configure(state='normal')
        self.water_Td_spinbox.configure(state='normal')
        self.column1_level_setpoint_spinbox.configure(state='normal')
        self.column1_level_entry.configure(state='readonly')
        self.column1_delta_p_entry.configure(state='readonly')
        self.column1_manual_switch.configure(state='normal')
        self.column1_scale.configure(state='normal')
        self.column1_manual_override_spinbox.configure(state='normal')
        self.column1_level_valve_entry.configure(state='readonly')
        self.column1_Kc_spinbox.configure(state='normal')
        self.column1_Ti_spinbox.configure(state='normal')
        self.column1_Td_spinbox.configure(state='normal')
        self.column2_level_setpoint_spinbox.configure(state='normal')
        self.column2_level_entry.configure(state='readonly')
        self.column2_delta_p_entry.configure(state='readonly')
        self.column2_manual_switch.configure(state='normal')
        self.column2_scale.configure(state='normal')
        self.column2_manual_override_spinbox.configure(state='normal')
        self.column2_level_valve_entry.configure(state='readonly')
        self.column2_Kc_spinbox.configure(state='normal')
        self.column2_Ti_spinbox.configure(state='normal')
        self.column2_Td_spinbox.configure(state='normal')
        self.toggle_logging_button.configure(state='normal')

    def _disable_powered_controls(self):
        self.air_flow_setpoint_spinbox.configure(state='disabled')
        self.air_flow_entry.configure(state='disabled')
        self.co2_concentration_entry.configure(state='disabled')
        self.water_flow_setpoint_spinbox.configure(state='disabled')
        self.water_flowrate_entry.configure(state='disabled')
        self.water_temperature_entry.configure(state='disabled')
        self.water_manual_switch.configure(state='disabled')
        self.water_scale.configure(state='disabled')
        self.water_manual_override_spinbox.configure(state='disabled')
        self.water_flow_valve_entry.configure(state='disabled')
        self.water_Kp_spinbox.configure(state='disabled')
        self.water_Ti_spinbox.configure(state='disabled')
        self.water_Td_spinbox.configure(state='disabled')
        self.column1_level_setpoint_spinbox.configure(state='disabled')
        self.column1_level_entry.configure(state='disabled')
        self.column1_delta_p_entry.configure(state='disabled')
        self.column1_manual_switch.configure(state='disabled')
        self.column1_scale.configure(state='disabled')
        self.column1_manual_override_spinbox.configure(state='disabled')
        self.column1_level_valve_entry.configure(state='disabled')
        self.column1_Kc_spinbox.configure(state='disabled')
        self.column1_Ti_spinbox.configure(state='disabled')
        self.column1_Td_spinbox.configure(state='disabled')
        self.column2_level_setpoint_spinbox.configure(state='disabled')
        self.column2_level_entry.configure(state='disabled')
        self.column2_delta_p_entry.configure(state='disabled')
        self.column2_manual_switch.configure(state='disabled')
        self.column2_scale.configure(state='disabled')
        self.column2_manual_override_spinbox.configure(state='disabled')
        self.column2_level_valve_entry.configure(state='disabled')
        self.column2_Kc_spinbox.configure(state='disabled')
        self.column2_Ti_spinbox.configure(state='disabled')
        self.column2_Td_spinbox.configure(state='disabled')
        self.toggle_logging_button.configure(state='disabled')

    def update_column_selector(self, *args):
        if self.handle is None:
            return
        try:
            if self.column_selector_boolean.get():
                self._safe_write(self.column_selector_output, 0)
            else:
                self._safe_write(self.column_selector_output, 5)
        except Exception as exc:
            print(f"Error updating column selector: {exc}")

    def light_or_dark_mode(self):
        self.a.set(1 - self.a.get())
        mode = 'dark' if self.a.get() else 'light'
        self.light_or_dark.config(text="Light Mode" if self.a.get() else "Dark Mode")
        self.style.theme_use(f'forest-{mode}')
        bg_color = self.style.lookup('.', 'background')
        self.root.configure(background=bg_color)
        self.water_flow_valve_output_frame.configure(background=bg_color)
        self.column1_level_valve_output_frame.configure(background=bg_color)
        self.column2_level_valve_output_frame.configure(background=bg_color)
        self.logo_frame.configure(background=bg_color)
        self.root.update_idletasks()

    def update_air_flowrate_entry(self):
        try:
            value = self._safe_read(self.air_flowrate_input)
            flowrate = 527.53746 * value - 250.26377
            self.air_flowrate_var.set(f"{flowrate:.2f}")
        except Exception:
            self.air_flowrate_var.set("Error")
        self.root.after(500, self.update_air_flowrate_entry)

    def update_air_flow_output(self):
        try:
            voltage = float(self.air_flowrate_setpoint_var.get()) / 200
            self._safe_write(self.air_setpoint_output, voltage)
        except Exception as exc:
            print(f"Error: {exc}")
        self.root.after(500, self.update_air_flow_output)

    def update_co2_concentration_entry(self):
        try:
            if not self.co2_concentration_input:
                raise ValueError("CO2 input not configured")
            value = self._safe_read(self.co2_concentration_input)
            self.co2_concentration_var.set(f"{value:.3f}")
        except Exception:
            self.co2_concentration_var.set("Error")
        self.root.after(500, self.update_co2_concentration_entry)

    def update_water_flowrate_entry(self):
        try:
            value = self._safe_read(self.water_flowrate_input)
            flowrate = 26.35046 * value - 12.35837
            self.water_flowrate_var.set(f"{flowrate:.2f}")
        except Exception:
            self.water_flowrate_var.set("Error")
        self.root.after(500, self.update_water_flowrate_entry)

    def update_water_temperature_entry(self):
        try:
            value = self._safe_read(self.water_temperature_input)
            m = 100 / (2.373 - 0.477)
            b = -20 - 0.477 * m
            temp = m * value + b
            self.water_temperature_var.set(f"{temp:.2f}")
        except Exception:
            self.water_temperature_var.set("Error")
        self.root.after(500, self.update_water_temperature_entry)

    def update_column1_level_entry(self):
        try:
            value = self._safe_read(self.column1_level_input)
            height_psi = (value - 0.478) / 1.896
            height_mmWc = max(0, height_psi * 703)
            self.column1_level_var.set(f"{height_mmWc:.2f}")
        except Exception:
            self.column1_level_var.set("Error")
        self.root.after(500, self.update_column1_level_entry)

    def update_column1_delta_p_entry(self):
        try:
            value = self._safe_read(self.column1_pressure_drop_input)
            pressure_drop_wc = 100 * (value - 0.476) / (2.373 - 0.476)
            pressure_drop_Pa = max(0, pressure_drop_wc * 248.84)
            self.column1_pressure_drop_var.set(f"{pressure_drop_Pa:.2f}")
        except Exception:
            self.column1_pressure_drop_var.set("Error")
        self.root.after(500, self.update_column1_delta_p_entry)

    def update_column2_level_entry(self):
        try:
            value = self._safe_read(self.column2_level_input)
            height_psi = (value - 0.478) / 1.896
            height_mmWc = max(0, height_psi * 703)
            self.column2_level_var.set(f"{height_mmWc:.2f}")
        except Exception:
            self.column2_level_var.set("Error")
        self.root.after(500, self.update_column2_level_entry)

    def update_column2_delta_p_entry(self):
        try:
            value = self._safe_read(self.column2_pressure_drop_input)
            pressure_drop_wc = 100 * (value - 0.476) / (2.373 - 0.476)
            pressure_drop_Pa = max(0, pressure_drop_wc * 248.84)
            self.column2_pressure_drop_var.set(f"{pressure_drop_Pa:.2f}")
        except Exception:
            self.column2_pressure_drop_var.set("Error")
        self.root.after(500, self.update_column2_delta_p_entry)

    def PID(self, Kc, Ti, Td, setpoint, measurement, dt, integral, e_prev):
        e_current = setpoint - measurement
        P = Kc * e_current

        if Ti > 0:
            Ki = Kc / Ti
            potential_integral = integral + (Ki * e_current * dt)
        else:
            potential_integral = integral

        D = (Kc * Td) * (e_current - e_prev) / dt
        u_raw = P + potential_integral + D

        if u_raw > 5:
            u_clamped = 5.0
            if e_current < 0 and Ti > 0:
                integral = potential_integral
        elif u_raw < 0:
            u_clamped = 0.0
            if e_current > 0 and Ti > 0:
                integral = potential_integral
        else:
            u_clamped = u_raw
            if Ti > 0:
                integral = potential_integral

        e_prev = e_current
        return u_clamped, integral, e_prev

    def auto_update_water_control_valve(self):
        if self.water_manual_override_boolean:
            try:
                setpoint = float(self.water_flowrate_setpoint_var.get())
                measurement = float(self.water_flowrate_var.get())
                Kp = self.water_Kc.get()
                Ti = self.water_Ti.get()
                Td = self.water_Td.get()
                dt = 0.5 / 60
                u, self.integral_w, self.e_prev_w = self.PID(
                    Kp,
                    Ti,
                    Td,
                    setpoint,
                    measurement,
                    dt,
                    getattr(self, 'integral_w', 0.0),
                    getattr(self, 'e_prev_w', 0.0),
                )
                self._safe_write(self.water_flowrate_output, u)
                self.g.set(u * 20)
            except ValueError:
                pass
            except Exception as exc:
                print(exc)
        self.root.after(500, self.auto_update_water_control_valve)

    def manual_update_water_control_valve(self):
        if not self.water_manual_override_boolean:
            try:
                val = 0.05 * int(self.rounded_g.get())
                self._safe_write(self.water_flowrate_output, val)
            except Exception as exc:
                print(exc)
        self.root.after(500, self.manual_update_water_control_valve)

    def water_manual_override_button(self):
        self.water_manual_override_boolean = not self.water_manual_override_boolean
        self.water_manual_switch.config(text="Mode: AUTO" if self.water_manual_override_boolean else "Mode: MANUAL")

    def auto_update_column1_control_valve(self):
        if self.column1_manual_override_boolean and self.column_selector_boolean.get():
            try:
                setpoint = float(self.column1_level_setpoint_var.get())
                measurement = float(self.column1_level_var.get())
                Kp = self.column1_Kc.get()
                Ti = self.column1_Ti.get()
                Td = self.column1_Td.get()
                dt = 0.5 / 60
                u, self.integral_1, self.e_prev_1 = self.PID(
                    Kp,
                    Ti,
                    Td,
                    setpoint,
                    measurement,
                    dt,
                    getattr(self, 'integral_1', 0.0),
                    getattr(self, 'e_prev_1', 0.0),
                )
                self._safe_write(self.column1_level_output, u)
                self.g1.set(u * 20)
            except ValueError:
                pass
            except Exception as exc:
                print(exc)
        self.root.after(500, self.auto_update_column1_control_valve)

    def manual_update_column1_control_valve(self):
        if not self.column1_manual_override_boolean and self.column_selector_boolean.get():
            try:
                val = 0.05 * int(self.rounded_g1.get())
                self._safe_write(self.column1_level_output, val)
            except Exception as exc:
                print(exc)
        self.root.after(500, self.manual_update_column1_control_valve)

    def column1_manual_override_button(self):
        self.column1_manual_override_boolean = not self.column1_manual_override_boolean
        self.column1_manual_switch.config(text="Mode: AUTO" if self.column1_manual_override_boolean else "Mode: MANUAL")

    def auto_update_column2_control_valve(self):
        if self.column2_manual_override_boolean and not self.column_selector_boolean.get():
            try:
                setpoint = float(self.column2_level_setpoint_var.get())
                measurement = float(self.column2_level_var.get())
                Kp = self.column2_Kc.get()
                Ti = self.column2_Ti.get()
                Td = self.column2_Td.get()
                dt = 0.5 / 60
                u, self.integral_2, self.e_prev_2 = self.PID(
                    Kp,
                    Ti,
                    Td,
                    setpoint,
                    measurement,
                    dt,
                    getattr(self, 'integral_2', 0.0),
                    getattr(self, 'e_prev_2', 0.0),
                )
                self._safe_write(self.column2_level_output, u)
                self.g2.set(u * 20)
            except ValueError:
                pass
            except Exception as exc:
                print(exc)
        self.root.after(500, self.auto_update_column2_control_valve)

    def manual_update_column2_control_valve(self):
        if not self.column2_manual_override_boolean and not self.column_selector_boolean.get():
            try:
                val = 0.05 * int(self.rounded_g2.get())
                self._safe_write(self.column2_level_output, val)
            except Exception as exc:
                print(exc)
        self.root.after(500, self.manual_update_column2_control_valve)

    def column2_manual_override_button(self):
        self.column2_manual_override_boolean = not self.column2_manual_override_boolean
        self.column2_manual_switch.config(text="Mode: AUTO" if self.column2_manual_override_boolean else "Mode: MANUAL")

    def generate_filename(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"data_log_{timestamp}.csv"

    def log_data(self):
        filename = self.generate_filename()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        folder_path = os.path.join(script_dir, "PackedColumns_LoggedData")
        os.makedirs(folder_path, exist_ok=True)
        file_path = os.path.join(folder_path, filename)

        with open(file_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "Time",
                "Water Temp (C)",
                "Water Flowrate (l/min)",
                "Air Flowrate (SLPM)",
                "Column #1 Pressure Drop (Pa)",
                "Column 2 Pressure Drop (Pa)",
            ])

            while not self.stop_event.is_set():
                timestamp = datetime.now().strftime("%H:%M:%S")
                writer.writerow([
                    timestamp,
                    self.water_temperature_var.get(),
                    self.water_flowrate_var.get(),
                    self.air_flowrate_var.get(),
                    self.column1_pressure_drop_var.get(),
                    self.column2_pressure_drop_var.get(),
                ])
                self.data_point_count_var.set(self.data_point_count_var.get() + 1)
                time.sleep(self.time_between_data_var.get())

        print(f"Data logging stopped. Data saved to {filename}")

    def toggle_logging(self):
        if not self.is_logging:
            self.is_logging = True
            self.stop_event.clear()
            self.logging_text_var.set("Stop Logging")
            self.data_point_count_entry.configure(state="readonly")
            Thread(target=self.log_data).start()
        else:
            self.is_logging = False
            self.stop_event.set()
            self.logging_text_var.set("Start Logging")
            self.data_point_count_var.set(0)
            self.data_point_count_entry.configure(state="disabled")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _commit_water_manual(self, event=None):
        try:
            val = float(self.rounded_g.get())
            self.g.set(val)
        except ValueError:
            pass

    def _commit_column1_manual(self, event=None):
        try:
            val = float(self.rounded_g1.get())
            self.g1.set(val)
        except ValueError:
            pass

    def _commit_column2_manual(self, event=None):
        try:
            val = float(self.rounded_g2.get())
            self.g2.set(val)
        except ValueError:
            pass

    def _update_water_spinbox_from_scale(self, *args):
        if self.root.focus_get() != self.water_manual_override_spinbox:
            self.rounded_g.set(round(self.g.get()))

    def _update_column1_spinbox_from_scale(self, *args):
        if self.root.focus_get() != self.column1_manual_override_spinbox:
            self.rounded_g1.set(round(self.g1.get()))

    def _update_column2_spinbox_from_scale(self, *args):
        if self.root.focus_get() != self.column2_manual_override_spinbox:
            self.rounded_g2.set(round(self.g2.get()))


if __name__ == '__main__':
    PackedColumnsGuiApp()