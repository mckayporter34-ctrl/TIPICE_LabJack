#region Initialization
import tkinter as tk
from tkinter import ttk
from labjack import ljm
import csv
import time
from datetime import datetime
from threading import Thread, Event
import os
import struct

root = tk.Tk()
root.geometry("1350x900")
root.title("Packed Columns")
root.option_add("*tearOff", False) # This is always a good idea



# Make the app responsive
root.columnconfigure(index=0, weight=1)
root.columnconfigure(index=1, weight=1)
root.columnconfigure(index=2, weight=1)
root.rowconfigure(index=0, weight=1)
root.rowconfigure(index=1, weight=1)
root.rowconfigure(index=2, weight=1)

# Root scaling
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=1)


# --- One-time scaling setup ---
BASE_WIDTH = 1600   # resolution you designed on (adjust if needed)
BASE_HEIGHT = 900

screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()

scalef = min(screen_w / BASE_WIDTH, screen_h / BASE_HEIGHT)

# Pass scaling factor into Tcl before sourcing themes
root.tk.eval(f"set scalef {scalef:.3f}")

# Import the tcl file
root.tk.call('source', f'forest-dark.tcl')
root.tk.call('source', f'forest-light.tcl')

# --- Scrollable container ---
container = ttk.Frame(root)
container.pack(fill="both", expand=True)

# Canvas inside container
canvas = tk.Canvas(container)
canvas.pack(side="left", fill="both", expand=True)

# Vertical scrollbar
scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
scrollbar.pack(side="right", fill="y")

# Frame inside canvas (put your actual widgets here)
scrollable_frame = ttk.Frame(canvas)

# Connect the frame to the canvas
canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

# Update scrollable area whenever the frame changes size
def on_frame_configure(event):
    canvas.configure(scrollregion=canvas.bbox("all"))

def _on_mousewheel(event):
    # For Windows and macOS, use different event.delta signs
    canvas.yview_scroll(int(-1*(event.delta/120)), "units")

canvas.bind_all("<MouseWheel>", _on_mousewheel)        # Windows

scrollable_frame.bind("<Configure>", on_frame_configure)

scrollable_frame.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
scrollable_frame.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

# Set the theme with the theme_use method
ttk.Style().theme_use(f'forest-light')
style = ttk.Style()
style.configure("Green.TLabel", foreground="green")
style.configure("Red.TLabel", foreground="red")

# Options for connection menu
connection_menu_list = ["USB", "Ethernet", "Disconnect"]

# Initialize Labjack
handle = None
#endregion

#region Variables
# Create control variables
a = tk.IntVar()
b = tk.BooleanVar(value=True)
c = tk.BooleanVar()

e = tk.StringVar(value="Connect to Labjack")
f = tk.BooleanVar()
g = tk.DoubleVar(value=0.0)
g1 = tk.DoubleVar(value=0.0)
g2 = tk.DoubleVar(value=0.0)
h = tk.BooleanVar()
rounded_g = tk.IntVar()
rounded_g1 = tk.IntVar()
rounded_g2 = tk.IntVar()

liquid_temperature_input = "AIN6"

air_flowrate_setpoint_var = tk.StringVar(value = '0') # SLPM
air_flowrate_input = "AIN0"
air_flowrate_var = tk.StringVar() #SLPM

co2_concentration_input = ""
co2_concentration_var = tk.StringVar()

water_flowrate_setpoint_var = tk.StringVar(value='0')
water_flowrate_input = "AIN1"
water_flowrate_output = "DAC1"
water_flowrate_var = tk.StringVar() # LPM

water_temperature_input = "AIN6"
water_temperature_var = tk.StringVar()

column1_pressure_drop_input = "AIN2"
column1_pressure_drop_var = tk.StringVar()

column2_pressure_drop_input = "AIN3"
column2_pressure_drop_var = tk.StringVar()

column1_level_input = "AIN4"
column1_level_setpoint_var = tk.StringVar(value='0')
column1_level_var = tk.StringVar()

column2_level_input = "AIN5"
column2_level_setpoint_var = tk.StringVar(value='0')
column2_level_var = tk.StringVar()

column1_level_output = "DAC0"
column2_level_output = "DAC0"
air_setpoint_output = "TDAC0"

main_power_output = "FIO6"
column_selector_output = "FIO7"

logging_text_var = tk.StringVar(value='Start Logging')
time_between_data_var = tk.DoubleVar(value = 1.0)
data_point_count_var = tk.IntVar(value = 0)

water_Kc = tk.IntVar(value = 1)
column1_Kc = tk.IntVar(value = 1)
column2_Kc = tk.IntVar(value = 1)
water_Ti = tk.IntVar(value = 1)
column1_Ti = tk.IntVar(value = 1)
column2_Ti = tk.IntVar(value = 1)
water_Td = tk.IntVar(value = 1)
column1_Td = tk.IntVar(value = 1)
column2_Td = tk.IntVar(value = 1)

main_power_boolean = False
water_manual_override_boolean = False
column1_manual_override_boolean = False
column2_manual_override_boolean = False
column_selector_boolean = tk.BooleanVar(value=True)
is_logging = False
stop_event = Event()

integral_w = 0.0
e_prev_w = 0.0
integral_1 = 0.0
e_prev_1 = 0.0
integral_2 = 0.0
e_prev_2 = 0.0

# I2C addresses
SCD30_ADDR = 0x61
MUX_ADDR = 0x70  # PCA9546 default

#endregion

#region Control Frame

# Create Control Frame
control_frame = ttk.LabelFrame(scrollable_frame, text="Controls", padding=(20, 10))
control_frame.grid(row=0, column=0, padx=(20, 10), pady=(10, 10), sticky="nsew")

# Create buttons in Controls frame
connect_dropdown = ttk.OptionMenu(control_frame, e,"Connect to Labjack", *connection_menu_list,
                                  command=lambda choice: connect_to_labjack(choice))
connect_dropdown.grid(row=0, column=0, padx=5, pady=(10,5), sticky="nsew")

connection_status = ttk.Label(control_frame, text="Connection Status", padding=(5, 5))
connection_status.grid(row=1, column=0, padx=5, pady=0, sticky="nsew")

power_switch = ttk.Checkbutton(control_frame, text="Main Power", style="Switch", command=lambda: main_power())
power_switch.grid(row=2, column=0, padx=5, pady=10, sticky="nsew")

column1_selector = ttk.Radiobutton(control_frame, text="Column 1 (White)", variable=column_selector_boolean, value=True)
column1_selector.grid(row=4, column=0, padx=5, pady=10, sticky="nsew")
column2_selector = ttk.Radiobutton(control_frame, text="Column 2 (Blue)", variable=column_selector_boolean, value=False)
column2_selector.grid(row=5, column=0, padx=5, pady=(5,5), sticky="nsew")
#endregion

#region Air Flow Frame

# Create Air Flow Frame
air_flow_frame = ttk.LabelFrame(scrollable_frame, text="Air Flow", padding=(20, 10))
air_flow_frame.grid(row=0, column=1, padx=(20, 10), pady=(10,10), sticky="nsew")

# Create widgets for Air Flow Frame
air_flow_setpoint_label = ttk.Label(air_flow_frame, text="Air Flow Setpoint (SLPM)")
air_flow_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="nsew")

air_flow_setpoint_spinbox = ttk.Spinbox(air_flow_frame, from_=0, to=1000,textvariable=air_flowrate_setpoint_var, width=5, state="disabled")
air_flow_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5,10), sticky="nsew")

air_flow_label = ttk.Label(air_flow_frame, text="Air Flow (SLPM)")
air_flow_label.grid(row=2, column=0, padx=5, pady=(10,0), sticky="nsew")

air_flow_entry = ttk.Entry(air_flow_frame, width=10, textvariable=air_flowrate_var, state="readonly")
air_flow_entry.grid(row=3, column=0, padx=5, pady=(5,10), sticky="nsew")

co2_concentration_label = ttk.Label(air_flow_frame, text="Delta CO2 Concentration (ppm)")
co2_concentration_label.grid(row=4, column=0, padx=5, pady=(10,0), sticky="nsew")

co2_concentration_entry = ttk.Entry(air_flow_frame, width=10, textvariable=co2_concentration_var, state="readonly")
co2_concentration_entry.grid(row=5, column=0, padx=5, pady=(5,10), sticky="nsew")
#endregion

#region Data Logging

data_logging_frame = ttk.LabelFrame(scrollable_frame, text="Data Logging", padding=(20, 10))
data_logging_frame.grid(row=1, column=0, columnspan=2, padx=(20, 10), pady=(10,10), sticky="nsew")

time_between_data_label = ttk.Label(data_logging_frame, text="Time Between Data")
time_between_data_label.grid(row=0, column=1, padx=5, pady=(20,5), sticky="nsew")
time_between_data_spinbox = ttk.Spinbox(data_logging_frame, from_=0, to=100, textvariable=time_between_data_var,
                                          width=5, state="normal")
time_between_data_spinbox.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

data_point_count_label = ttk.Label(data_logging_frame, text="Data Point Count")
data_point_count_label.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")
data_point_count_entry = ttk.Entry(data_logging_frame, textvariable=data_point_count_var, state="disabled")
data_point_count_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

toggle_logging_button = ttk.Checkbutton(data_logging_frame, textvariable=logging_text_var, style="ToggleButton",
                                        command= lambda: toggle_logging(),padding=(20,20))
toggle_logging_button.grid(row=0, rowspan=4, column=0, padx=40, pady=(20,5), sticky="nsew")


#endregion

#region Sperator
separator = ttk.Separator(scrollable_frame)
separator.grid(row=0, column=2, rowspan=3, padx=(20, 10), pady=10, sticky="ns")
#endregion

#region Logo
######################## Create Toggle Mode and tipice logo ############################
logo_frame = tk.LabelFrame(scrollable_frame, borderwidth=0,relief = "flat")
logo_frame.grid(row=2, column=0, columnspan=2, padx=(40, 10), pady=(0,0), sticky="nsew")

img = tk.PhotoImage(file="tipice_logo.png")
logo = ttk.Label(logo_frame, image=img)
logo.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

logo_label = ttk.Label(logo_frame, text="BYU TIPICE", font=("Copperplate Gothic Bold", 60), wraplength=300)
logo_label.grid(row=0, column=1, padx=(5,20), pady=5, sticky="nsew")

light_or_dark = ttk.Checkbutton(logo_frame, text="Dark Mode", style="ToggleButton", command =lambda: light_or_dark_mode())
light_or_dark.grid(row=1, column=0, columnspan=2, padx=5, pady=10)
#endregion

#region Water Frame

water_frame = ttk.LabelFrame(scrollable_frame, text="Water", padding=(20, 10))
water_frame.grid(row=0, column=3, columnspan=3, padx=(20, 20), pady=(10,10), sticky="nsew")

# Widget for Water Frame
# Column 0
water_flow_setpoint_label = ttk.Label(water_frame, text="Water Flowrate Setpoint (l/min)")
water_flow_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")
water_flow_setpoint_spinbox = ttk.Spinbox(water_frame, from_=0, to=50, textvariable=water_flowrate_setpoint_var,
                                          width=5, state="disabled")
water_flow_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5,10), sticky="ew")

water_flowrate_label = ttk.Label(water_frame, text="Water Flowrate (l/min)")
water_flowrate_label.grid(row=2, column=0, padx=5, pady=(10,0), sticky="nsew")
water_flowrate_entry = ttk.Entry(water_frame, textvariable=water_flowrate_var, state="disabled" , width=10)
water_flowrate_entry.grid(row=3, column=0, padx=5, pady=(5,10), sticky="ew")

water_temperature_label = ttk.Label(water_frame, text="Water Temp (C)")
water_temperature_label.grid(row=4, column=0, padx=5, pady=(10,0), sticky="nsew")
water_temperature_entry = ttk.Entry(water_frame, textvariable=water_temperature_var, state="readonly" , width=10)
water_temperature_entry.grid(row=5, column=0, padx=5, pady=(5,10), sticky="ew")

# Column 1-2
# Update value in spinbox according to scale
updating_w = False

def update_rounded_g(*args):
    """Update the rounded display when g changes."""
    global updating_w
    if not updating_w:
        try:
            updating_w = True
            rounded_g.set(round(g.get()))  # Update rounded display
        except ValueError:
            pass
        finally:
            updating_w = False

def update_g(*args):
    """Update g when rounded_g (Spinbox) changes."""
    global updating_w
    if not updating_w:
        try:
            updating_w = True
            g.set(float(rounded_g.get()))  # Update g with rounded value
            updating_w = False
        except ValueError:
            pass  # Ignore invalid input
        finally:
            updating_w = False

water_override_label = ttk.Label(water_frame, width=20, text="Manual Override")
water_override_label.grid(row=0, column=1, columnspan=3,padx=(40,0), pady=0, sticky="nsew")
water_manual_switch = ttk.Checkbutton(water_frame, text="Auto", style="Switch",
                                      command=lambda: water_manual_override_button())
water_manual_switch.grid(row=1, column=1, columnspan=3, padx=(40,0), pady=(5,10), sticky="ew")

water_set_manual_label = ttk.Label(water_frame, text="Set Manual Valve Output")
water_set_manual_label.grid(row=2, column=1, columnspan=4, padx=(40,0), pady=(10,0), sticky="nsew")

water_scale = ttk.Scale(water_frame, from_=0, to=100, variable=g)
water_scale.grid(row=3, column=1,columnspan=3, padx=(40,5), pady=(5, 0), sticky="ew")

water_manual_override_spinbox = ttk.Spinbox(water_frame, from_=0, to=100, width=3, textvariable=rounded_g,
                                            state="normal")
water_manual_override_spinbox.grid(row=3, column=4, padx=5, pady=(5,10), sticky="ew")
water_manual_override_spinbox.bind("<Return>", lambda event: update_g())
water_manual_override_spinbox.set(round(g.get()))

# Bind the change of g to the update_spinbox function
g.trace_add("write", update_rounded_g)
rounded_g.trace_add("write", update_g)

water_scale_label_0 = ttk.Label(water_frame, text="0", anchor='w')
water_scale_label_0.grid(row=4, column=1, padx=(40,0), pady=0, sticky="ew")
water_scale_label_50 = ttk.Label(water_frame, text="   50", anchor='center')
water_scale_label_50.grid(row=4, column=2, padx=0, pady=0, sticky="ew")
water_scale_label_100 = ttk.Label(water_frame, text="100", anchor='e')
water_scale_label_100.grid(row=4, column=3, padx=0, pady=0, sticky="ew")

#Column 5
water_flow_valve_output_frame = tk.LabelFrame(water_frame, borderwidth=0,relief = "flat")
water_flow_valve_output_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=(0,0), sticky="nsew")

water_flow_valve_output_label = ttk.Label(water_flow_valve_output_frame, text="Flow Valve Output (%)")
water_flow_valve_output_label.grid(row=0, column=0,columnspan=3, padx=0, pady=0, sticky="nsew")
water_flow_valve_output_label.grid_propagate(False)

water_progress_label_0 = ttk.Label(water_flow_valve_output_frame, text="100", anchor='ne')
water_progress_label_0.grid(row=1, column=0, padx=(0,0), pady=0, sticky="ew")
water_progress_label_50 = ttk.Label(water_flow_valve_output_frame, text="50")
water_progress_label_50.grid(row=2, column=0, padx=0, pady=(10,0), sticky="e")
water_progress_label_100 = ttk.Label(water_flow_valve_output_frame, text="0", anchor='se')
water_progress_label_100.grid(row=3, column=0, padx=0, pady=0, sticky="se")

progress = ttk.Progressbar(water_flow_valve_output_frame, orient="vertical", value=0, variable=g, mode="determinate")
progress.grid(row=1, rowspan=3, column=1, padx=(0, 0), pady=(10, 0), sticky="ns")

water_flow_valve_entry = ttk.Entry(water_flow_valve_output_frame,state="readonly",textvariable=rounded_g, width=5)
water_flow_valve_entry.grid(row=1, column=2, padx=(5,0), pady=0, sticky="ew")


#Column 6-7
water_Kp_label = ttk.Label(water_frame, text="Kc")
water_Kp_label.grid(row=0, column=6, columnspan=2, padx=40, pady=0, sticky="nsew")

water_Kp_spinbox = ttk.Spinbox(water_frame, textvariable=water_Kc, from_=0, to=100, width=5, state="disabled")
water_Kp_spinbox.grid(row=1, column=6, padx=(40,0), pady=(5,10), sticky="ew")

water_Ti_label = ttk.Label(water_frame, text="Ti")
water_Ti_label.grid(row=2, column=6, columnspan=2, padx=40, pady=(10,0), sticky="nsew")

water_Ti_spinbox = ttk.Spinbox(water_frame, textvariable=water_Ti, from_=0, to=100, width=5, state="disabled")
water_Ti_spinbox.grid(row=3, column=6, padx=(40,0), pady=(5,10), sticky="ew")
water_Ti_units_label = ttk.Label(water_frame, text="(min)")
water_Ti_units_label.grid(row=3, column=7, padx=(5,0), pady=(5,10), sticky="nsew")

water_Td_label = ttk.Label(water_frame, text="Td")
water_Td_label.grid(row=4, column=6, columnspan=2, padx=40, pady=(10,0), sticky="nsew")

water_Td_spinbox = ttk.Spinbox(water_frame, textvariable=water_Td, from_=0, to=100, width=5, state="disable")
water_Td_spinbox.grid(row=5, column=6, padx=(40,0), pady=(5,10), sticky="nsew")
water_Td_units_label = ttk.Label(water_frame, text="(min)")
water_Td_units_label.grid(row=5, column=7, padx=(5,0), pady=(5,10), sticky="nsew")
#endregion

#region Column 1 Frame

column1_frame = ttk.LabelFrame(scrollable_frame, text="Column 1", padding=(20, 10))
column1_frame.grid(row=1, column=3, columnspan=3, padx=(20, 20), pady=(10,10), sticky="nsew")

# Widgert for Water Frame
#Column 0
column1_level_setpoint_label = ttk.Label(column1_frame, text="Column 1 Level Setpoint (mm)")
column1_level_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")
column1_level_setpoint_spinbox = ttk.Spinbox(column1_frame, from_=0, to=100, textvariable=column1_level_setpoint_var, width=5, state="disabled")
column1_level_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5,10), sticky="ew")

column1_level_label = ttk.Label(column1_frame, text="Column 1 Level (mm)")
column1_level_label.grid(row=2, column=0, padx=5, pady=(10,0), sticky="nsew")
column1_level_entry = ttk.Entry(column1_frame, textvariable=column1_level_var, state="readonly" , width=10)
column1_level_entry.grid(row=3, column=0, padx=5, pady=(5,10), sticky="ew")

column1_delta_p_label = ttk.Label(column1_frame, text="Column 1 Pressure Drop (Pa)")
column1_delta_p_label.grid(row=4, column=0, padx=5, pady=(10,0), sticky="nsew")
column1_delta_p_entry = ttk.Entry(column1_frame, textvariable=column1_pressure_drop_var, width=10)
column1_delta_p_entry.grid(row=5, column=0, padx=5, pady=(5,10), sticky="nsew")

#Column 1-2

#Update value in spinbox according to scale
updating_1 = False

def update_rounded_g1(*args):
    """Update the rounded display when g changes."""
    global updating_1
    if not updating_1:
        try:
            updating_1 = True
            rounded_g1.set(round(g1.get()))  # Update rounded display
        except ValueError:
            pass
        finally:
            updating_1 = False

def update_g1(*args):
    """Update g when rounded_g (Spinbox) changes."""
    global updating_1
    if not updating_1:
        try:
            updating_1 = True
            g1.set(float(rounded_g1.get()))  # Update g with rounded value
            updating_1 = False
        except ValueError:
            pass  # Ignore invalid input
        finally:
            updating_1 = False

column1_override_label = ttk.Label(column1_frame, width=20, text="Manual Override")
column1_override_label.grid(row=0, column=1, columnspan=3,padx=(40,0), pady=0, sticky="nsew")
column1_manual_switch = ttk.Checkbutton(column1_frame, text="Auto", style="Switch", command=lambda: column1_manual_override_button())
column1_manual_switch.grid(row=1, column=1, columnspan=3, padx=(40,0), pady=(5,10), sticky="ew")

column1_set_manual_label = ttk.Label(column1_frame, text="Set Manual Valve Output")
column1_set_manual_label.grid(row=2, column=1, columnspan=4, padx=(40,0), pady=(10,0), sticky="nsew")

column1_scale = ttk.Scale(column1_frame, from_=0, to=100, variable=g1)
column1_scale.grid(row=3, column=1,columnspan=3, padx=(40,5), pady=(5, 0), sticky="ew")
#command=lambda: g.set(float(water_manual_override_spinbox.get()))
column1_manual_override_spinbox = ttk.Spinbox(column1_frame, from_=0, to=100, width=3, textvariable=rounded_g1, state="normal")
column1_manual_override_spinbox.grid(row=3, column=4, padx=5, pady=(5,10), sticky="ew")
column1_manual_override_spinbox.bind("<Return>", lambda event: g1.set(float(column1_manual_override_spinbox.get())))
column1_manual_override_spinbox.set(round(g1.get()))

# Bind the change of g to the update_spinbox function
g1.trace_add("write", update_rounded_g1)
rounded_g1.trace_add("write", update_g1)


column1_scale_label_0 = ttk.Label(column1_frame, text="0", anchor='w')
column1_scale_label_0.grid(row=4, column=1, padx=(40,0), pady=0, sticky="ew")
column1_scale_label_50 = ttk.Label(column1_frame, text="   50", anchor='center')
column1_scale_label_50.grid(row=4, column=2, padx=0, pady=0, sticky="ew")
column1_scale_label_100 = ttk.Label(column1_frame, text="100", anchor='e')
column1_scale_label_100.grid(row=4, column=3, padx=0, pady=0, sticky="ew")

#Column 5
column1_level_valve_output_frame = tk.LabelFrame(column1_frame, borderwidth=0,relief = "flat")
column1_level_valve_output_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=(0,0), sticky="nsew")

column1_level_valve_output_label = ttk.Label(column1_level_valve_output_frame, text="Flow Valve Output (%)")
column1_level_valve_output_label.grid(row=0, column=0,columnspan=3, padx=0, pady=0, sticky="nsew")
column1_level_valve_output_label.grid_propagate(False)

column1_progress_label_0 = ttk.Label(column1_level_valve_output_frame, text="100", anchor='ne')
column1_progress_label_0.grid(row=1, column=0, padx=(0,0), pady=0, sticky="ew")
column1_progress_label_50 = ttk.Label(column1_level_valve_output_frame, text="50")
column1_progress_label_50.grid(row=2, column=0, padx=0, pady=(10,0), sticky="e")
column1_progress_label_100 = ttk.Label(column1_level_valve_output_frame, text="0", anchor='se')
column1_progress_label_100.grid(row=3, column=0, padx=0, pady=0, sticky="se")

column1_progress = ttk.Progressbar(column1_level_valve_output_frame, orient="vertical", value=0, variable=g1, mode="determinate")
column1_progress.grid(row=1, rowspan=3, column=1, padx=(0, 0), pady=(10, 0), sticky="ns")

column1_level_valve_entry = ttk.Entry(column1_level_valve_output_frame,state="readonly",textvariable=rounded_g1, width=5)
column1_level_valve_entry.grid(row=1, column=2, padx=(5,0), pady=0, sticky="ew")


#Column 6-7
column1_Kc_label = ttk.Label(column1_frame, text="Kc")
column1_Kc_label.grid(row=0, column=6, columnspan=2, padx=40, pady=0, sticky="nsew")

column1_Kc_spinbox = ttk.Spinbox(column1_frame, textvariable=column1_Kc, from_=0, to=100, width=5, state="disabled")
column1_Kc_spinbox.grid(row=1, column=6, padx=(40,0), pady=(5,10), sticky="ew")

column1_Ti_label = ttk.Label(column1_frame, text="Ti")
column1_Ti_label.grid(row=2, column=6, columnspan=2, padx=40, pady=(10,0), sticky="nsew")

column1_Ti_spinbox = ttk.Spinbox(column1_frame, textvariable=column1_Ti, from_=0, to=100, width=5, state="disabled")
column1_Ti_spinbox.grid(row=3, column=6, padx=(40,0), pady=(5,10), sticky="ew")
column1_Ti_units_label = ttk.Label(column1_frame, text="(min)")
column1_Ti_units_label.grid(row=3, column=7, padx=(5,0), pady=(5,10), sticky="nsew")

column1_Td_label = ttk.Label(column1_frame, text="Td")
column1_Td_label.grid(row=4, column=6, columnspan=2, padx=40, pady=(10,0), sticky="nsew")

column1_Td_spinbox = ttk.Spinbox(column1_frame, textvariable=column1_Td, from_=0, to=100, width=5, state="disable")
column1_Td_spinbox.grid(row=5, column=6, padx=(40,0), pady=(5,10), sticky="nsew")
column1_Td_units_label = ttk.Label(column1_frame, text="(min)")
column1_Td_units_label.grid(row=5, column=7, padx=(5,0), pady=(5,10), sticky="nsew")
#endregion

#region Column 2 Frame

column2_frame = ttk.LabelFrame(scrollable_frame, text="Column 2", padding=(20, 10))
column2_frame.grid(row=2, column=3, columnspan=3, padx=(20, 20), pady=(10,10), sticky="nsew")

# Widgert for Water Frame
# Column 0
column2_level_setpoint_label = ttk.Label(column2_frame, text="Column 2 Level Setpoint (mm)")
column2_level_setpoint_label.grid(row=0, column=0, padx=5, pady=0, sticky="ew")
column2_level_setpoint_spinbox = ttk.Spinbox(column2_frame, from_=0, to=100, textvariable=column2_level_setpoint_var, width=5, state="disabled")
column2_level_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5,10), sticky="ew")

column2_level_label = ttk.Label(column2_frame, text="Column 2 Level (mm)")
column2_level_label.grid(row=2, column=0, padx=5, pady=(10,0), sticky="nsew")
column2_level_entry = ttk.Entry(column2_frame, textvariable=column2_level_var, state="readonly" , width=10)
column2_level_entry.grid(row=3, column=0, padx=5, pady=(5,10), sticky="ew")

column2_delta_p_label = ttk.Label(column2_frame, text="Column 2 Pressure Drop (Pa)")
column2_delta_p_label.grid(row=4, column=0, padx=5, pady=(10,0), sticky="nsew")
column2_delta_p_entry = ttk.Entry(column2_frame, textvariable=column2_pressure_drop_var, width=10)
column2_delta_p_entry.grid(row=5, column=0, padx=5, pady=(5,10), sticky="nsew")

# Column 1-2
# Update value in spinbox according to scale
updating_2 = False

def update_rounded_g2(*args):
    """Update the rounded display when g changes."""
    global updating_2
    if not updating_2:
        try:
            updating_2 = True
            rounded_g2.set(round(g2.get()))  # Update rounded display
        except ValueError:
            pass
        finally:
            updating_2 = False

def update_g2(*args):
    """Update g when rounded_g (Spinbox) changes."""
    global updating_2
    if not updating_2:
        try:
            updating_2 = True
            g2.set(float(rounded_g2.get()))  # Update g with rounded value
        except ValueError:
            pass  # Ignore invalid input
        finally:
            updating_2 = False

column2_override_label = ttk.Label(column2_frame, width=20, text="Manual Override")
column2_override_label.grid(row=0, column=1, columnspan=3,padx=(40,0), pady=0, sticky="nsew")
column2_manual_switch = ttk.Checkbutton(column2_frame, text="Auto", style="Switch", command=lambda: column2_manual_override_button())
column2_manual_switch.grid(row=1, column=1, columnspan=3, padx=(40,0), pady=(5,10), sticky="ew")

column2_set_manual_label = ttk.Label(column2_frame, text="Set Manual Valve Output")
column2_set_manual_label.grid(row=2, column=1, columnspan=4, padx=(40,0), pady=(10,0), sticky="nsew")

column2_scale = ttk.Scale(column2_frame, from_=0, to=100, variable=g2)
column2_scale.grid(row=3, column=1,columnspan=3, padx=(40,5), pady=(5, 0), sticky="ew")

column2_manual_override_spinbox = ttk.Spinbox(column2_frame, from_=0, to=100, width=3, textvariable=rounded_g2, state="normal")
column2_manual_override_spinbox.grid(row=3, column=4, padx=5, pady=(5,10), sticky="ew")
column2_manual_override_spinbox.bind("<Return>", lambda event: g2.set(float(column1_manual_override_spinbox.get())))
column2_manual_override_spinbox.set(round(g2.get()))

# Bind the change of g to the update_spinbox function
g2.trace_add("write", update_rounded_g2)
rounded_g2.trace_add("write", update_g2)


column2_scale_label_0 = ttk.Label(column2_frame, text="0", anchor='w')
column2_scale_label_0.grid(row=4, column=1, padx=(40,0), pady=0, sticky="ew")
column2_scale_label_50 = ttk.Label(column2_frame, text="   50", anchor='center')
column2_scale_label_50.grid(row=4, column=2, padx=0, pady=0, sticky="ew")
column2_scale_label_100 = ttk.Label(column2_frame, text="100", anchor='e')
column2_scale_label_100.grid(row=4, column=3, padx=0, pady=0, sticky="ew")

#Column 5
column2_level_valve_output_frame = tk.LabelFrame(column2_frame, borderwidth=0,relief = "flat")
column2_level_valve_output_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=(0,0), sticky="nsew")

column2_level_valve_output_label = ttk.Label(column2_level_valve_output_frame, text="Flow Valve Output (%)")
column2_level_valve_output_label.grid(row=0, column=0,columnspan=3, padx=0, pady=0, sticky="nsew")
column2_level_valve_output_label.grid_propagate(False)

column2_progress_label_0 = ttk.Label(column2_level_valve_output_frame, text="100", anchor='ne')
column2_progress_label_0.grid(row=1, column=0, padx=(0,0), pady=0, sticky="ew")
column2_progress_label_50 = ttk.Label(column2_level_valve_output_frame, text="50")
column2_progress_label_50.grid(row=2, column=0, padx=0, pady=(10,0), sticky="e")
column2_progress_label_100 = ttk.Label(column2_level_valve_output_frame, text="0", anchor='se')
column2_progress_label_100.grid(row=3, column=0, padx=0, pady=0, sticky="se")

column2_progress = ttk.Progressbar(column2_level_valve_output_frame, orient="vertical", value=0, variable=g2, mode="determinate")
column2_progress.grid(row=1, rowspan=3, column=1, padx=(0, 0), pady=(10, 0), sticky="ns")

column2_level_valve_entry = ttk.Entry(column2_level_valve_output_frame,state="readonly",textvariable=rounded_g2, width=5)
column2_level_valve_entry.grid(row=1, column=2, padx=(5,0), pady=0, sticky="ew")


#Column 6-7
column2_Kc_label = ttk.Label(column2_frame, text="Kc")
column2_Kc_label.grid(row=0, column=6, columnspan=2, padx=40, pady=0, sticky="nsew")

column2_Kc_spinbox = ttk.Spinbox(column2_frame, textvariable=column2_Kc, from_=0, to=100, width=5, state="disabled")
column2_Kc_spinbox.grid(row=1, column=6, padx=(40,0), pady=(5,10), sticky="ew")

column2_Ti_label = ttk.Label(column2_frame, text="Ti")
column2_Ti_label.grid(row=2, column=6, columnspan=2, padx=40, pady=(10,0), sticky="nsew")

column2_Ti_spinbox = ttk.Spinbox(column2_frame, textvariable=column2_Ti, from_=0, to=100, width=5, state="disabled")
column2_Ti_spinbox.grid(row=3, column=6, padx=(40,0), pady=(5,10), sticky="ew")
column2_Ti_units_label = ttk.Label(column2_frame, text="(min)")
column2_Ti_units_label.grid(row=3, column=7, padx=(5,0), pady=(5,10), sticky="nsew")

column2_Td_label = ttk.Label(column2_frame, text="Td")
column2_Td_label.grid(row=4, column=6, columnspan=2, padx=40, pady=(10,0), sticky="nsew")

column2_Td_spinbox = ttk.Spinbox(column2_frame, textvariable=column2_Td, from_=0, to=100, width=5, state="disable")
column2_Td_spinbox.grid(row=5, column=6, padx=(40,0), pady=(5,10), sticky="nsew")
column2_Td_units_label = ttk.Label(column2_frame, text="(min)")
column2_Td_units_label.grid(row=5, column=7, padx=(5,0), pady=(5,10), sticky="nsew")
#endregion

#region Functions
def connect_to_labjack(choice):
    if choice == "USB":
        connect("T7", "USB", "ANY")
    elif choice == "Ethernet":
        connect("T7", "ETHERNET", "10.8.112.59")
    elif choice == "Disconnect":
        disconnect()

def connect(T7, connection_type, identifier):
    global handle
    try:
        handle = ljm.openS(T7, connection_type, identifier)
        connection_status.config(text="Connected", style="Green.TLabel")
        ljm.eWriteName(handle, "I2C_SPEED_THROTTLE", 65536)  # Slows bus to ~10 kHz
        #ljm.eWriteName(handle, f"DIO6_DIRECTION", 1)
        #ljm.eWriteName(handle, f"DIO7_DIRECTION", 1)
    except Exception as e:
        handle = None
        connection_status.config(text='Failed to connect to LabJack', style="Red.TLabel")
        print(e)

def disconnect():
    global handle
    if handle:
        ljm.close(handle)
        handle = None
        connection_status.config(text="LabJack disconnected", style="Green.TLabel")

def main_power():
    global main_power_boolean
    main_power_boolean = not main_power_boolean
    try:
        if main_power_boolean:
            ljm.eWriteName(handle, main_power_output, 1)
            air_flow_setpoint_spinbox.configure(state='normal')
            air_flow_entry.configure(state="readonly")
            co2_concentration_entry.configure(state='readonly')
            water_flow_setpoint_spinbox.configure(state='normal')
            water_flowrate_entry.configure(state="readonly")
            water_temperature_entry.configure(state="readonly")
            water_manual_switch.configure(state="normal")
            water_scale.configure(state="normal")
            water_manual_override_spinbox.configure(state="normal")
            water_flow_valve_entry.configure(state="readonly")
            water_Kp_spinbox.configure(state="normal")
            water_Ti_spinbox.configure(state="normal")
            water_Td_spinbox.configure(state="normal")
            column1_level_setpoint_spinbox.configure(state="normal")
            column1_level_entry.configure(state="readonly")
            column1_delta_p_entry.configure(state="readonly")
            column1_manual_switch.configure(state="normal")
            column1_scale.configure(state="normal")
            column1_manual_override_spinbox.configure(state="normal")
            column1_level_valve_entry.configure(state="readonly")
            column1_Kc_spinbox.configure(state="normal")
            column1_Ti_spinbox.configure(state="normal")
            column1_Td_spinbox.configure(state="normal")
            column2_level_setpoint_spinbox.configure(state="normal")
            column2_level_entry.configure(state="readonly")
            column2_delta_p_entry.configure(state="readonly")
            column2_manual_switch.configure(state="normal")
            column2_scale.configure(state="normal")
            column2_manual_override_spinbox.configure(state="normal")
            column2_level_valve_entry.configure(state="readonly")
            column2_Kc_spinbox.configure(state="normal")
            column2_Ti_spinbox.configure(state="normal")
            column2_Td_spinbox.configure(state="normal")
            toggle_logging_button.configure(state="normal")

        else:
            ljm.eWriteName(handle, main_power_output, 0)
            air_flow_setpoint_spinbox.configure(state=tk.DISABLED)
            air_flow_entry.configure(state=tk.DISABLED)
            co2_concentration_entry.configure(state=tk.DISABLED)
            water_flow_setpoint_spinbox.configure(state=tk.DISABLED)
            water_flowrate_entry.configure(state=tk.DISABLED)
            water_temperature_entry.configure(state=tk.DISABLED)
            water_manual_switch.configure(state=tk.DISABLED)
            water_scale.configure(state=tk.DISABLED)
            water_manual_override_spinbox.configure(state=tk.DISABLED)
            water_flow_valve_entry.configure(state=tk.DISABLED)
            water_Kp_spinbox.configure(state=tk.DISABLED)
            water_Ti_spinbox.configure(state=tk.DISABLED)
            water_Td_spinbox.configure(state=tk.DISABLED)
            column1_level_setpoint_spinbox.configure(state=tk.DISABLED)
            column1_level_entry.configure(state=tk.DISABLED)
            column1_delta_p_entry.configure(state=tk.DISABLED)
            column1_manual_switch.configure(state=tk.DISABLED)
            column1_scale.configure(state=tk.DISABLED)
            column1_manual_override_spinbox.configure(state=tk.DISABLED)
            column1_level_valve_entry.configure(state=tk.DISABLED)
            column1_Kc_spinbox.configure(state=tk.DISABLED)
            column1_Ti_spinbox.configure(state=tk.DISABLED)
            column1_Td_spinbox.configure(state=tk.DISABLED)
            column2_level_setpoint_spinbox.configure(state=tk.DISABLED)
            column2_level_entry.configure(state=tk.DISABLED)
            column2_delta_p_entry.configure(state=tk.DISABLED)
            column2_manual_switch.configure(state=tk.DISABLED)
            column2_scale.configure(state=tk.DISABLED)
            column2_manual_override_spinbox.configure(state=tk.DISABLED)
            column2_level_valve_entry.configure(state=tk.DISABLED)
            column2_Kc_spinbox.configure(state=tk.DISABLED)
            column2_Ti_spinbox.configure(state=tk.DISABLED)
            column2_Td_spinbox.configure(state=tk.DISABLED)
            toggle_logging_button.configure(state=tk.DISABLED)

    except Exception as e:
        print(f"Error: {e}")
        #connection_status.configure(text="Error")

def update_column_selector():
    try:
        if column_selector_boolean.get():
            ljm.eWriteName(handle, column_selector_output, 0) #output 0V if column 1 is selected
        else:
            ljm.eWriteName(handle, column_selector_output, 5) #output 5V if column 2 is selected
    except Exception as e:
        print(f"Error: {e}")
update_column_selector()
column_selector_boolean.trace_add('write', lambda *args: update_column_selector())

def light_or_dark_mode():
    a.set(1-a.get())
    mode ='dark' if a.get() else 'light'
    light_or_dark.config(text=f"Light Mode" if a.get() else f"Dark Mode")

    style = ttk.Style()
    style.theme_use(f'forest-{mode}')

    # Get new background color
    bg_color = style.lookup(".", "background")

    # Set root and all widgets with new background color
    root.configure(background=bg_color)
    water_flow_valve_output_frame.configure(background=bg_color)
    column1_level_valve_output_frame.configure(background=bg_color)
    column2_level_valve_output_frame.configure(background=bg_color)
    logo_frame.configure(background=bg_color)

    root.update_idletasks()

def update_air_flowrate_entry():
    try:
        value = ljm.eReadName(handle, air_flowrate_input)  # Change "AIN2" to your desired pin

        # convert voltage(0.4744-2.3728) to SLPM(0-1000)
        flowrate = 527.53746 * value - 250.26377

        air_flowrate_var.set(f"{flowrate:.2f}")  # Update the entry widget with formatted value
    except Exception as e:
        air_flowrate_var.set("Error")  # Handle errors gracefully
    root.after(500, update_air_flowrate_entry)  # Call this function again after 500ms
update_air_flowrate_entry()

def update_air_flow_output():
    try:
        #convert SLPM to voltage(0-5)
        voltage = float(air_flowrate_setpoint_var.get()) / 200

        ljm.eWriteName(handle, air_setpoint_output, voltage)
    except Exception as e:
        print(f"Error: {e}")
    root.after(500, update_air_flow_output)
update_air_flow_output()

def update_co2_concentration_entry():
    try:
        value = ljm.eReadName(handle, co2_concentration_input)  # Change "AIN2" to your desired pin
        co2_concentration_var.set(f"{value:.3f}")  # Update the entry widget with formatted value
    except Exception as e:
        co2_concentration_var.set("Error")  # Handle errors gracefully
    root.after(500, update_co2_concentration_entry)  # Call this function again after 500ms
update_co2_concentration_entry()

def update_water_flowrate_entry():
    try:
        value = ljm.eReadName(handle, water_flowrate_input)

        #convert voltage(0.469-2.3665) to lpm(0-50)
        flowrate = 26.35046 * value - 12.35837

        water_flowrate_var.set(f"{flowrate:.2f}")
    except Exception as e:
        water_flowrate_var.set("Error")
    root.after(500, update_water_flowrate_entry)
update_water_flowrate_entry()

def update_water_temperature_entry():
    try:
        value = ljm.eReadName(handle, water_temperature_input)

        #convert voltage(0.477-2.373) to temp in C (-20 - 80)
        m = 100 / (2.373 - 0.477)
        b = -20 - 0.477 * m
        temp = m * value + b

        water_temperature_var.set(f"{temp:.2f}")
    except Exception as e:
        water_temperature_var.set("Error")
    root.after(500, update_water_temperature_entry)
update_water_temperature_entry()

def update_column1_level_entry():
    try:
        value = ljm.eReadName(handle, column1_level_input)

        #convert voltage(0.478-2.374) to psi (0-1psi)
        height_psi = (value - 0.478) / 1.896
        #cover psi to mm Wc
        height_mmWc = height_psi * 703
        height_mmWc = max(0, height_mmWc)

        column1_level_var.set(f"{height_mmWc:.2f}")
    except Exception as e:
        column1_level_var.set("Error")
    root.after(500, update_column1_level_entry)
update_column1_level_entry()

def update_column1_delta_p_entry():
    try:
        value = ljm.eReadName(handle, column1_pressure_drop_input)

        #convert voltage(0-5) to inWC (0-100)
        pressure_drop_wc = 100 * (value - 0.476) / (2.373-0.476)
        #convert inWC to Pa
        pressure_drop_Pa = pressure_drop_wc * 248.84
        pressure_drop_Pa = max(0, pressure_drop_Pa)

        column1_pressure_drop_var.set(f"{pressure_drop_Pa:.2f}")
    except Exception as e:
        column1_pressure_drop_var.set("Error")
    root.after(500, update_column1_delta_p_entry)
update_column1_delta_p_entry()

def update_column2_level_entry():
    try:
        value = ljm.eReadName(handle, column2_level_input)

        # convert voltage(0-5) to mm water column (0-703mm)
        height_psi = (value - 0.478) / 1.896
        height_mmWc = height_psi * 703
        height_mmWc = max(0, height_mmWc)

        column2_level_var.set(f"{height_mmWc:.2f}")
    except Exception as e:
        column2_level_var.set("Error")
    root.after(500, update_column2_level_entry)
update_column2_level_entry()

def update_column2_delta_p_entry():
    try:
        value = ljm.eReadName(handle, column2_pressure_drop_input)

        # convert voltage(0-5) to inWC (0-100)
        pressure_drop_wc = 100 * (value - 0.476) / (2.373 - 0.476)
        # convert inWC to Pa
        pressure_drop_Pa = pressure_drop_wc * 248.84
        pressure_drop_Pa = max(0, pressure_drop_Pa)

        column2_pressure_drop_var.set(f"{pressure_drop_Pa:.2f}")
    except Exception as e:
        column2_pressure_drop_var.set("Error")
    root.after(500, update_column2_delta_p_entry)
update_column2_delta_p_entry()

def PID(Kc, Ti, Td, setpoint, measurement, dt, integral, e_prev):
    Ki = Kc / Ti
    Kd = Kc * Td

    # PID calculations
    e_current = setpoint - measurement
    P = Kc * e_current
    integral += Ki * e_current * dt
    D = Kd * (e_current - e_prev) / dt

    # Compute raw control output
    u_raw = P + integral + D

    # Clamp output between 0V and 5V
    u_clamped = max(0, min(u_raw, 5))

    # Update stored values for next iteration
    e_prev = e_current

    return u_clamped, integral, e_prev

def auto_update_water_control_valve():
    global water_manual_override_boolean, integral_w, e_prev_w
    if water_manual_override_boolean:
        try:
            Kp = water_Kc.get()
            Ti = water_Ti.get()
            Td = water_Td.get()
            setpoint = float(water_flowrate_setpoint_var.get())
            measurement = float(water_flowrate_var.get())
            dt = 0.5 / 60 # is 0.5 seconds converted to minutes becuase Ti and Td are in minutes
            u, integral_w, e_prev_w = PID(Kp, Ti, Td, setpoint, measurement, dt, integral_w, e_prev_w) # u is the voltage sent to the control valve
            ljm.eWriteName(handle, water_flowrate_output, u)
            rounded_g.set(round(u * 20,2)) # set g to 0 - 100 proportional to 0 - 5 V
        except Exception as e:
            print(e)
        root.after(500, auto_update_water_control_valve)

def manual_update_water_control_valve():
    global water_manual_override_boolean
    if not water_manual_override_boolean:
        try:
            val =  0.05 * int(rounded_g.get()) #converts a value from 0 to 100 to a value from 0 to 5
            ljm.eWriteName(handle, water_flowrate_output, val)
        except Exception as e:
            print(e)
        root.after(500,  manual_update_water_control_valve)
manual_update_water_control_valve()

def water_manual_override_button():
    global water_manual_override_boolean
    water_manual_override_boolean = not water_manual_override_boolean
    if water_manual_override_boolean:
        auto_update_water_control_valve()
    else:
        manual_update_water_control_valve()

def auto_update_column1_control_valve():
    global column1_manual_override_boolean, integral_1, e_prev_1
    if column1_manual_override_boolean and column_selector_boolean.get():
        try:
            Kp = column1_Kc.get()
            Ti = column1_Ti.get()
            Td = column1_Td.get()
            setpoint = float(column1_level_setpoint_var.get())
            measurement = float(column1_level_var.get())
            dt = 0.5 / 60 # is 0.5 seconds converted to minutes becuase Ti and Td are in minutes
            u, integral_1, e_prev_1 = PID(Kp, Ti, Td, setpoint, measurement, dt, integral_1, e_prev_1) # u is the voltage sent to the control valve
            ljm.eWriteName(handle, column1_level_output, u)
            rounded_g1.set(round(u * 20,2)) # set g to 0 - 100 proportional to 0 - 5 V
        except Exception as e:
            print(e)
        root.after(500, auto_update_column1_control_valve)

def manual_update_column1_control_valve():
    global column1_manual_override_boolean
    if not column1_manual_override_boolean:
        try:
            val =  0.05 * int(rounded_g1.get()) #converts a value from 0 to 100 to a value from 0 to 5
            if column_selector_boolean.get():
                ljm.eWriteName(handle, column1_level_output, val)
            else: pass
        except Exception as e:
            print(e)
        root.after(500,  manual_update_column1_control_valve)
manual_update_column1_control_valve()

def column1_manual_override_button():
    global column1_manual_override_boolean
    column1_manual_override_boolean = not column1_manual_override_boolean
    if column1_manual_override_boolean:
        auto_update_column1_control_valve()
    else:
        manual_update_column1_control_valve()

def auto_update_column2_control_valve():
    global column2_manual_override_boolean, integral_2, e_prev_2
    if column2_manual_override_boolean and not column_selector_boolean.get():
        try:
            Kp = column2_Kc.get()
            Ti = column2_Ti.get()
            Td = column2_Td.get()
            setpoint = float(column2_level_setpoint_var.get())
            measurement = float(column2_level_var.get())
            dt = 0.5 / 60 # is 0.5 seconds converted to minutes becuase Ti and Td are in minutes
            u, integral_2, e_prev_2 = PID(Kp, Ti, Td, setpoint, measurement, dt, integral_2, e_prev_2) # u is the voltage sent to the control valve
            ljm.eWriteName(handle, column2_level_output, u)
            rounded_g2.set(round(u * 20,2)) # set g to 0 - 100 proportional to 0 - 5 V
        except Exception as e:
            print(e)
        root.after(500, auto_update_column2_control_valve)

def manual_update_column2_control_valve():
    global column2_manual_override_boolean
    if not column2_manual_override_boolean:
        try:
            val =  0.05 * int(rounded_g2.get()) #converts a value from 0 to 100 to a value from 0 to 5
            if not column_selector_boolean.get():
                ljm.eWriteName(handle, column2_level_output, val)
            else: pass
        except Exception as e:
            print(e)
        root.after(500,  manual_update_column2_control_valve)
manual_update_column2_control_valve()

def column2_manual_override_button():
    global column2_manual_override_boolean
    column2_manual_override_boolean = not column2_manual_override_boolean
    if column2_manual_override_boolean:
        auto_update_column2_control_valve()
    else:
        manual_update_column2_control_valve()

def generate_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"data_log_{timestamp}.csv"

def log_data():
    # Generate a unique filename for the CSV
    filename = generate_filename()

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the subfolder name
    folder_name = "PackedColumns_LoggedData"

    # Create the full path for the new folder
    folder_path = os.path.join(script_dir, folder_name)

    # Create the folder if it doesn't exist
    os.makedirs(folder_path, exist_ok=True)

    # Construct the full file path
    file_path = os.path.join(folder_path, filename)

    with open(file_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Time", "Water Temp (C)", 'Water Flowrate (l/min)', 'Air Flowrate (SPLM)',
                         'Column #1 Pressure Drop (Pa)', 'Column 2 Pressure Drop (Pa)', 'Ambient Temp (C)',
                         'Ambient Pressure (kPa)' ]) #column headers

        while not stop_event.is_set():
            timestamp = datetime.now().strftime("%H:%M:%S")

            writer.writerow([timestamp, water_temperature_var.get(), water_flowrate_var.get(), air_flowrate_var.get(),
                             column1_pressure_drop_var.get(), column2_pressure_drop_var.get()]) #fill with values to put in each cell in the row
            data_point_count_var.set(data_point_count_var.get() + 1) # Update counter
            time.sleep(time_between_data_var.get())  # Delay between readings

    print(f"Data logging stopped. Data saved to {filename}")

def toggle_logging():
    global is_logging
    if not is_logging:
        # Start logging
        is_logging = True
        stop_event.clear()
        logging_text_var.set("Stop Logging")
        data_point_count_entry.configure(state="readonly")

        # Run logging in a separate thread to avoid blocking the GUI
        logging_thread = Thread(target=log_data)
        logging_thread.start()
    else:
        # Stop logging
        is_logging = False
        stop_event.set()
        logging_text_var.set("Start Logging")
        data_point_count_var.set(0)
        data_point_count_entry.configure(state="disabled")

#endregion

root.mainloop()