import tkinter as tk
from tkinter import ttk
from labjack import ljm
import csv
import time
from datetime import datetime
from threading import Thread, Event
import os

class LabJackGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("LabJack T7 GUI")

        # Initialize LabJack handle
        self.handle = None

        self.is_logging = False
        self.stop_event = Event()

        # Create the main frame
        self.main_frame = tk.Frame(master, bg="#ffffff")
        self.main_frame.pack(expand=True, fill="both")

        # Create the connection frame
        self.connection_frame = tk.LabelFrame(self.main_frame, text="Connection", bg="#ffffff", fg="#0047ba", padx=10, pady=10)
        self.connection_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        for i in range(2):  # Adjust for number of columns
            self.connection_frame.columnconfigure(i, weight=1)

        # Create widgets for the connection frame
        self.label = tk.Label(self.connection_frame, text="Lab Jack T7 Connection", font=("Calibri", 16), fg="#0072ce", bg="#ffffff")
        self.label.grid(row=0, column=0, columnspan=2, pady=5)
       
        self.connection_type = tk.StringVar()
        self.connection_type.set("Connect")  # Placeholder text

        # Create an OptionMenu dropdown to connecto to labjack
        self.connect_menu = tk.OptionMenu(self.connection_frame, self.connection_type, "USB", "Ethernet", command=self.handle_selection)
        self.connect_menu.config(bg="#bdd6e6", fg="#002e5d", relief="flat", borderwidth=0, highlightbackground="#ffffff")
        self.connect_menu.grid(row=1, column=0, padx=5, pady=5)

        self.disconnect_button = tk.Button(self.connection_frame, text="Disconnect", command=self.disconnect, \
                                           width=10, bg="#bdd6e6", fg="#002e5d", relief="flat", state=tk.DISABLED)
        self.disconnect_button.grid(row=1, column=1, padx=5, pady=5)

        self.status_label = tk.Label(self.connection_frame, text="", font=("Arial", 12), bg="#ffffff", fg="#00966C")
        self.status_label.grid(row=2, column=0, columnspan=2, pady=5)

        # Create the control frame
        self.control_frame = tk.LabelFrame(self.main_frame, text="Control", fg="#0047ba", bg="#ffffff", padx=10, pady=10)
        self.control_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        for i in range(6):  # Adjust for number of columns
            self.control_frame.columnconfigure(i, weight=1)


        # Create widgets for the control frame
        self.tdac2_label = tk.Label(self.control_frame, text="Pump Flow Rate", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.tdac2_label.grid(row=0, column=0, columnspan=6, pady=5)

        self.tdac2_display_label = tk.Label(self.control_frame, text="", font=("Arial", 12), bg="#ffffff")
        self.tdac2_display_label.grid(row=1, column=0, columnspan=6, pady=5)

        self.tdac2_up_button = tk.Button(self.control_frame, text="+", command=lambda: self.set_tdac2_speed(1), width=15,\
                                         bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.tdac2_up_button.grid(row=2, column=0, columnspan=3, padx=5, pady=5)

        self.tdac2_down_button = tk.Button(self.control_frame, text="-", command=lambda: self.set_tdac2_speed(-1), width=15,\
                                           bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.tdac2_down_button.grid(row=2, column=3, columnspan=3, padx=5, pady=5)

        self.speed0_button = tk.Button(self.control_frame, text="0", command=lambda: self.set_speed(0), width=4,\
                                       bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.speed0_button.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        self.speed4_button = tk.Button(self.control_frame, text="4", command=lambda: self.set_speed(4), width=4,\
                                       bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.speed4_button.grid(row=3, column=2, columnspan=2, padx=5, pady=5)

        self.speed8_button = tk.Button(self.control_frame, text="8", command=lambda: self.set_speed(8), width=4,\
                                       bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.speed8_button.grid(row=3, column=4, columnspan=2, padx=5, pady=5)

        self.fio0_label = tk.Label(self.control_frame, text="Pump Controller", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.fio0_label.grid(row=4, column=0, columnspan=6, pady=5)

        #self.set_fio0_output_button = tk.Button(self.control_frame, text="Set as Output", command=self.set_fio0_output, width=15)
        #self.set_fio0_output_button.grid(row=4, column=0, padx=5, pady=5)

        self.toggle_fio0_state_button = tk.Button(self.control_frame, text="On/Off", command=self.toggle_fio0_state, width=15,\
                                                  bg="#bdd6e6", fg="#002e5d", relief="flat", state=tk.DISABLED)
        self.toggle_fio0_state_button.grid(row=5, column=0, columnspan=6, padx=5, pady=5)

        # Create the analog input frame
        self.analog_input_frame = tk.LabelFrame(self.main_frame, text="Data", bg="#ffffff", fg="#0047BA", padx=10, pady=10)
        self.analog_input_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")


        # Create widgets for the analog input frame
        self.read_inputs = tk.Button(self.analog_input_frame, text="Read Data", command=self.read_analog_inputs, width=15,\
                                     bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.read_inputs.grid(row=4, column=1, padx=5, pady=5)

        self.ani0_label = tk.Label(self.analog_input_frame, text="Temp:", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.ani0_label.grid(row=0, column=0, pady=5)

        self.ani0_display_label = tk.Label(self.analog_input_frame, text="", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.ani0_display_label.grid(row=0, column=1, pady=5)

        self.ani1_label = tk.Label(self.analog_input_frame, text="Flow Rate:", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.ani1_label.grid(row=1, column=0, pady=5)

        self.ani1_display_label = tk.Label(self.analog_input_frame, text="", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.ani1_display_label.grid(row=1, column=1, pady=5)

        self.ani2_label = tk.Label(self.analog_input_frame, text="Pressure:", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.ani2_label.grid(row=2, column=0, pady=5)

        self.ani2_display_label = tk.Label(self.analog_input_frame, text="", font=("Calibri", 14), bg="#ffffff", fg="#0072ce")
        self.ani2_display_label.grid(row=2, column=1, pady=5)

        self.toggle_logging = tk.Button(self.analog_input_frame, text="Start Logging", command=self.toggle_logging, width=15,\
                                        bg="#bdd6e6", fg="#002e5d", relief="flat")
        self.toggle_logging.grid(row=5, column=1, padx=5, pady=5)

       

       
    def handle_selection(self, selection):
       
        if selection == "Ethernet":
            self.connect_Ethernet()
        elif selection == "USB":
            self.connect_USB()
    def connect_Ethernet(self):
        # Connect to LabJack T7
        try:
            self.handle = ljm.openS("T7", "ETHERNET", "10.8.112.140")
            self.status_label.config(text="Connected to LabJack T7", font=("Calibri", 14), fg="#8cc98f")
            self.connect_menu.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.tdac2_up_button.config(state=tk.NORMAL)
            self.tdac2_down_button.config(state=tk.NORMAL)
            #self.set_fio0_output_button.config(state=tk.NORMAL)
            self.toggle_fio0_state_button.config(state=tk.NORMAL)
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")
            self.disconnect_button.config(state=tk.NORMAL)
           
    def connect_USB(self):
        # Connect to LabJack T7
        try:
            self.handle = ljm.openS("T7", "USB", "ANY")
            self.status_label.config(text="Connected to LabJack T7", font=("Calibri", 14), fg="#8cc98f")
            self.connect_menu.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.tdac2_up_button.config(state=tk.NORMAL)
            self.tdac2_down_button.config(state=tk.NORMAL)
            #self.set_fio0_output_button.config(state=tk.NORMAL)
            self.toggle_fio0_state_button.config(state=tk.NORMAL)
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")

    def disconnect(self):
        # Disconnect from LabJack T7
        ljm.close(self.handle)
        self.status_label.config(text="Disconnected from LabJack T7", font=("Calibri", 14), fg="#8cc98f")
        self.connect_menu.config(state=tk.NORMAL)
        self.disconnect_button.config(state=tk.DISABLED)
        self.tdac2_up_button.config(state=tk.DISABLED)
        self.tdac2_down_button.config(state=tk.DISABLED)
        #self.set_fio0_output_button.config(state=tk.DISABLED)
        self.toggle_fio0_state_button.config(state=tk.DISABLED)

    def set_tdac2_speed(self, direction):
        # Adjust TDAC2 speed
        if self.handle is not None:
            try:
                current_speed = ljm.eReadName(self.handle, "DAC0") # TDAC is write only so I had to use DAC0 to keep track of the voltage
                new_speed = current_speed + direction * 0.25  # Adjust speed by 0.5 volts
                ljm.eWriteName(self.handle, "TDAC2", 2*new_speed)
                ljm.eWriteName(self.handle, "DAC0", new_speed)
                display_speed = round(2*new_speed, 2)
                self.tdac2_display_label.config(text=f"TDAC2: {display_speed} V", font=("Calibri", 14), fg="#8cc98f")
            except Exception as e:
                self.tdac2_display_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")
        else:
            self.tdac2_display_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")

    def set_speed(self, newval):
        if self.handle is not None:
            try:
                ljm.eWriteName(self.handle, "TDAC2", newval)
                ljm.eWriteName(self.handle, "DAC0", newval/2)
                self.tdac2_display_label.config(text=f"TDAC2: {newval} V", font=("Calibri", 14), fg="#8cc98f")
            except Exception as e:
                self.tdac2_display_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")
        else:
            self.tdac2_display_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")

    """
    def set_fio0_output(self):
        # Set FIO0 as digital output
        if self.handle is not None:
            try:
                ljm.eWriteName(self.handle, "FIO2", 0)  # Set FIO0 as digital output
                self.status_label.config(text="FIO0 set as output", font=("Calibri", 14), fg="#8cc98f")
                self.toggle_fio0_state_button.config(state=tk.NORMAL)
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="#ff5261")
        else:
            self.status_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")
    """
   
    def toggle_fio0_state(self):
        # Toggle FIO0 state
        if self.handle is not None:
            try:
                fio0_state = ljm.eReadName(self.handle, "FIO0")
                ljm.eWriteName(self.handle, "FIO0", 1 - fio0_state)  # Toggle FIO0 state
                onoff = int(1 - fio0_state)
                if onoff == 1:
                    self.status_label.config(text=f"Pump is off", font=("Calibri", 14), fg="#8cc98f")
                if onoff == 0:
                    self.status_label.config(text=f"Pump is on", font=("Calibri", 14), fg="#8cc98f")
            except Exception as e:
                self.status_label.config(text=f"Error: {e}", fg="#ff5261")
        else:
            self.status_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")
   
    def v_to_C(self, x):
        return round(((55.28745157*x)-48.08422656),2)
    def v_to_gpm(self, x):
        return round((((53.2187707*x)-25.35572892)*0.264172),2)
    def v_to_wc(self, x):
        return round(((3.125*8.475*x)-12.5),2)
       
    def read_analog_inputs(self):
        if self.handle is not None:
            try:
                ani0_value = ljm.eReadName(self.handle, "AIN0")
                ani1_value = ljm.eReadName(self.handle, "AIN1")
                ani2_value = ljm.eReadName(self.handle, "AIN2")
                temp_value = self.v_to_C(ani0_value)
                flow_value = self.v_to_gpm(ani1_value)
                pressure_value = self.v_to_wc(ani2_value)
                print(f"Temp: {temp_value} V")
                print(f"Flow Rate: {flow_value} V")
                print(f"/delta P: {pressure_value} V")
                self.ani0_display_label.config(text=f"{temp_value} C", font=("Calibri", 14), fg="#8cc98f")
                self.ani1_display_label.config(text=f"{flow_value} gpm", font=("Calibri", 14), fg="#8cc98f")
                self.ani2_display_label.config(text=f"{pressure_value} WC", font=("Calibri", 14), fg="#8cc98f")
            except Exception as e:
                print(f"Error reading analog inputs: {e}")
                self.ani0_display_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")
                self.ani1_display_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")
                self.ani2_display_label.config(text=f"Error: {e}", font=("Calibri", 14), fg="#ff5261")
        else:
            print("LabJack not connected")
            self.ani0_display_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")
            self.ani1_display_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")
            self.ani2_display_label.config(text="Error: LabJack not connected", font=("Calibri", 14), fg="#ff5261")

    def generate_filename(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"data_log_{timestamp}.csv"


    def log_data(self):
        # Generate a unique filename for the CSV
        filename = self.generate_filename()

        # Voltage to unit conversions

           

        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Define the subfolder name
        folder_name = "NNF_Lab_LoggedData"

        # Create the full path for the new folder
        folder_path = os.path.join(script_dir, folder_name)

        # Create the folder if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)

        # Construct the full file path
        file_path = os.path.join(folder_path, filename)

        with open(file_path, "w", newline="") as csvfile:

            writer = csv.writer(csvfile)
            writer.writerow(["Timestamp", "Temp in C", "Flow Rate in gpm", "Pressure Drop in \"wc"])

            while not self.stop_event.is_set():
                timestamp = datetime.now().strftime("%H:%M:%S")
                ani0_value = ljm.eReadName(self.handle, "AIN0")
                temp_value = self.v_to_C(ani0_value)
                ani1_value = ljm.eReadName(self.handle, "AIN1")
                flow_value = self.v_to_gpm(ani1_value)
                ani2_value = ljm.eReadName(self.handle, "AIN2")
                pressure_value = self.v_to_wc(ani2_value)
               
                writer.writerow([timestamp, temp_value, flow_value, pressure_value])
                print(f"Logged data: {timestamp}, Temp:, {temp_value} C")
                print(f"Logged data: {timestamp}, Flow Rate:, {flow_value} gpm")
                print(f"Logged data: {timestamp}, Pressure diff:, {pressure_value} \"WC")
               

                time.sleep(1)  # Delay between readings

        print(f"Data logging stopped. Data saved to {filename}")


    def toggle_logging(self):
        if not self.is_logging:
            # Start logging
            self.is_logging = True
            self.stop_event.clear()
            self.toggle_logging.config(text="Stop Logging")

            # Run logging in a separate thread to avoid blocking the GUI
            self.logging_thread = Thread(target=self.log_data)
            self.logging_thread.start()
        else:
            # Stop logging
            self.is_logging = False
            self.stop_event.set()
            self.toggle_logging.config(text="Start Logging")

def main():
    root = tk.Tk()
    gui = LabJackGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()