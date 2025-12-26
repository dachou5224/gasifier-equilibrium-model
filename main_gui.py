import tkinter as tk
from tkinter import ttk, messagebox, Menu
from gasifier import GasifierModel
from coal_props import COAL_DATABASE
from validation_cases import VALIDATION_CASES 

DEFAULT_INPUTS = {
    "Coal Analysis": {
        "Cd": ("Carbon (C)", 75.83), "Hd": ("Hydrogen (H)", 4.58),
        "Od": ("Oxygen (O)", 10.89), "Nd": ("Nitrogen (N)", 1.19),
        "Sd": ("Sulfur (S)", 0.29), "Ad": ("Ash", 7.22),
        "Vd": ("Volatiles (Vd)", 34.96), "FCd": ("Fixed Carbon", 57.82),
        "Mt": ("Total Moisture", 14.3), "HHV_Input": ("HHV (kJ/kg, Dry)", 30720.0) 
    },
    "Process Conditions": {
        "FeedRate": ("Feed Rate (kg/h)", 1000.0),
        "SlurryConc": ("Slurry Conc (wt%)", 60.0),
        "Ratio_OC": ("O2/Coal Ratio (kg/kg)", 0.8),
        "Ratio_SC": ("Steam/Coal Ratio (kg/kg)", 0.08),
        "pt": ("Oxygen Purity (%)", 99.6),
        "P":  ("Pressure (MPa)", 4.0),
        "TIN": ("Gas Inlet Temp (K)", 500.0),
        "HeatLossPercent": ("Heat Loss (% of HHV)", 1.0),
        "TR": ("Guess Temp (K)", 1500.0),
        "T_Scrubber": ("Scrubber Temp (°C)", 210.0) # [NEW] 用户接口
    }
}

class GasifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gasifier Equilibrium Model (Advanced)")
        self.root.geometry("1000x900") # 稍微调高窗口
        
        self.entries = {}
        self.hhv_method_var = tk.IntVar(value=0)
        self.type_var = tk.StringVar(value="Dry Powder")
        
        self._setup_menu() 
        self._setup_ui()
        self._toggle_inputs()

    def _setup_menu(self):
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        val_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Validation & Benchmarks", menu=val_menu)
        for case_name in VALIDATION_CASES.keys():
            val_menu.add_command(label=f"Load & Run: {case_name}", 
                                 command=lambda c=case_name: self.run_validation_case(c))

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        left_panel = ttk.Frame(main_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        row_idx = 0
        ttk.Label(left_panel, text="Step 1: Coal Properties", font=("Arial", 10, "bold"), foreground="blue").grid(row=row_idx, column=0, sticky="w", pady=5)
        
        self.coal_var = tk.StringVar()
        self.coal_combo = ttk.Combobox(left_panel, textvariable=self.coal_var, state="readonly", width=25)
        self.coal_combo['values'] = list(COAL_DATABASE.keys())
        self.coal_combo.grid(row=row_idx, column=1, sticky="w", padx=5)
        self.coal_combo.bind("<<ComboboxSelected>>", self.load_coal_data)
        row_idx += 1

        rb_frame = ttk.Frame(left_panel)
        rb_frame.grid(row=row_idx, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Radiobutton(rb_frame, text="DB/Input HHV", variable=self.hhv_method_var, value=0).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(rb_frame, text="Formula HHV", variable=self.hhv_method_var, value=1).pack(side=tk.LEFT, padx=5)
        row_idx += 1
        
        for key, (label_text, default_val) in DEFAULT_INPUTS["Coal Analysis"].items():
            ttk.Label(left_panel, text=label_text).grid(row=row_idx, column=0, sticky="e", padx=5)
            entry = ttk.Entry(left_panel, width=15)
            entry.insert(0, str(default_val))
            entry.grid(row=row_idx, column=1, sticky="w", padx=5)
            self.entries[key] = entry
            row_idx += 1

        ttk.Separator(left_panel, orient='horizontal').grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=10)
        row_idx += 1

        ttk.Label(left_panel, text="Step 2: Process Conditions", font=("Arial", 10, "bold"), foreground="blue").grid(row=row_idx, column=0, sticky="w", pady=5)
        row_idx += 1
        
        ttk.Label(left_panel, text="Gasifier Type:").grid(row=row_idx, column=0, sticky="e", padx=5)
        type_combo = ttk.Combobox(left_panel, textvariable=self.type_var, state="readonly", width=13)
        type_combo['values'] = ["Dry Powder", "CWS"] 
        type_combo.grid(row=row_idx, column=1, sticky="w", padx=5)
        type_combo.bind("<<ComboboxSelected>>", self._toggle_inputs)
        row_idx += 1

        self.process_widgets = {} 
        for key, (label_text, default_val) in DEFAULT_INPUTS["Process Conditions"].items():
            lbl = ttk.Label(left_panel, text=label_text)
            lbl.grid(row=row_idx, column=0, sticky="e", padx=5)
            entry = ttk.Entry(left_panel, width=15)
            entry.insert(0, str(default_val))
            entry.grid(row=row_idx, column=1, sticky="w", padx=5)
            self.entries[key] = entry
            self.process_widgets[key] = (lbl, entry) 
            row_idx += 1

        btn_frame = ttk.Frame(left_panel)
        btn_frame.grid(row=row_idx+1, column=0, columnspan=2, pady=20, sticky="ew")
        
        run_btn = ttk.Button(btn_frame, text="Run Simulation", command=self.run_simulation)
        run_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        cal_btn = ttk.Button(btn_frame, text="Auto-Calibrate Heat Loss", command=self.calibrate_heat_loss)
        cal_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Label(right_panel, text="Simulation Results", font=("Arial", 12, "bold")).pack(pady=(0, 10))
        self.result_text = tk.Text(right_panel, width=55, height=55)
        self.result_text.pack(fill=tk.BOTH, expand=True)

    def _toggle_inputs(self, event=None):
        g_type = self.type_var.get()
        lbl_feed, ent_feed = self.process_widgets['FeedRate']
        lbl_conc, ent_conc = self.process_widgets['SlurryConc']
        
        if g_type == "Dry Powder":
            lbl_feed.config(text="Dry Coal Feed (kg/h)")
            lbl_conc.grid_remove()
            ent_conc.grid_remove()
        else: 
            lbl_feed.config(text="Slurry Feed (kg/h)")
            lbl_conc.grid()
            ent_conc.grid()

    def load_coal_data(self, event):
        selected_coal = self.coal_var.get()
        if selected_coal in COAL_DATABASE:
            data = COAL_DATABASE[selected_coal]
            for key, value in data.items():
                if key in self.entries:
                    self.entries[key].delete(0, tk.END)
                    self.entries[key].insert(0, str(value))
            if 'HHV_d' in data:
                hhv_kj = data['HHV_d'] * 1000.0
                if 'HHV_Input' in self.entries:
                    self.entries['HHV_Input'].delete(0, tk.END)
                    self.entries['HHV_Input'].insert(0, str(hhv_kj))

    def run_validation_case(self, case_name):
        case_data = VALIDATION_CASES[case_name]
        inputs = case_data["inputs"]
        
        coal_data = inputs["Coal Analysis"]
        if coal_data == "SAME_AS_BASE":
            coal_data = VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]["Coal Analysis"]
            
        for key, val in coal_data.items():
            if key in self.entries:
                self.entries[key].delete(0, tk.END)
                self.entries[key].insert(0, str(val))
                
        proc_data = inputs["Process Conditions"]
        for key, val in proc_data.items():
            if key in self.entries:
                self.entries[key].delete(0, tk.END)
                self.entries[key].insert(0, str(val))
            if key == "GasifierType":
                self.type_var.set(val)
                self._toggle_inputs()
        
        # 验证时不校验水洗塔，直接运行
        self.run_simulation(validation_target=case_data.get("expected_output"))

    def calibrate_heat_loss(self):
        # (代码保持不变，请确保包含之前的校正逻辑)
        from tkinter import simpledialog
        target_T_C = simpledialog.askfloat("Smart Calibration", "Enter Target Outlet Temperature (°C):", initialvalue=1370.0)
        
        if target_T_C is None: return 
        target_T_K = target_T_C + 273.15
        
        input_data = {}
        try:
            for key, entry_widget in self.entries.items():
                input_data[key] = float(entry_widget.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid inputs.")
            return

        input_data['HHV_Method'] = self.hhv_method_var.get()
        input_data['GasifierType'] = self.type_var.get()
        
        try:
            model = GasifierModel(input_data)
            new_loss_pct, _ = model.calculate_heat_loss_for_target_T(target_T_K)
            
            if new_loss_pct < 0.1:
                answer = messagebox.askyesno(
                    "Calibration Strategy Change",
                    f"Calculated Heat Loss is unrealistic ({new_loss_pct:.2f}%).\n\n"
                    "This implies the current O2 is insufficient to reach {target_T_C}°C.\n"
                    "Do you want to fix Heat Loss at 1.0% and adjust O2/Coal Ratio instead?"
                )
                
                if answer:
                    fixed_loss = 1.0 
                    new_ratio_oc = model.calculate_oxygen_ratio_for_target_T(target_T_K, fixed_loss_percent=fixed_loss)
                    
                    self.entries['HeatLossPercent'].delete(0, tk.END)
                    self.entries['HeatLossPercent'].insert(0, f"{fixed_loss}")
                    self.entries['Ratio_OC'].delete(0, tk.END)
                    self.entries['Ratio_OC'].insert(0, f"{new_ratio_oc:.4f}")
                    
                    messagebox.showinfo("Success", f"New O/C: {new_ratio_oc:.4f}, Fixed Loss: 1.0%")
                    return

            self.entries['HeatLossPercent'].delete(0, tk.END)
            self.entries['HeatLossPercent'].insert(0, f"{new_loss_pct:.4f}")
            messagebox.showinfo("Success", f"New Heat Loss: {new_loss_pct:.4f}%")
                                
        except Exception as e:
            messagebox.showerror("Calibration Failed", f"Solver Error: {str(e)}")

    def run_simulation(self, validation_target=None):
        input_data = {}
        try:
            for key, entry_widget in self.entries.items():
                val_str = entry_widget.get()
                input_data[key] = float(val_str)
        except ValueError:
            messagebox.showerror("Error", "Invalid Input")
            return
            
        input_data['HHV_Method'] = self.hhv_method_var.get()
        input_data['GasifierType'] = self.type_var.get()

        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "Running simulation...\n")
        self.root.update()

        try:
            model = GasifierModel(input_data)
            res = model.run_simulation()
            
            output = f"""
=========================================
      GASIFIER SIMULATION REPORT
=========================================
[Operating Conditions]
Type: {input_data['GasifierType']}  |  P: {input_data['P']} MPa
O/C:  {input_data['Ratio_OC']}      |  S/C: {input_data['Ratio_SC']}

[Reactor Outlet Performance]
Outlet Temp:     {res['TOUT_C']:.2f} °C
Syngas (Dry):    {res['Vg_dry']:.2f} Nm3/h
H2O Content:     {res['Y_H2O_wet']:.2f} vol%
Heat Err:        {res['Heat_Err_Pct']:.4f}%

[Quench/Scrubber Outlet (@{res['T_Scrub']:.0f}°C)]
Total Wet Flow:  {res['Vg_Quench']:.2f} Nm3/h
Water/Gas Ratio: {res['WGR_Quench']:.4f} (mol H2O/mol Dry)
Assumption: Saturated with water vapor.

[Dry Gas Composition (vol%)]
CO:    {res['Y_CO_dry']:.2f} %
H2:    {res['Y_H2_dry']:.2f} %
CO2:   {res['Y_CO2_dry']:.2f} %
N2:    {res['Y_N2_dry']:.2f} %
CH4:   {res['Y_CH4_dry']:.2f} %

[Wet Gas Composition (Reactor Outlet)]
CO:    {res['Y_CO_wet']:.2f} %
H2:    {res['Y_H2_wet']:.2f} %
CO2:   {res['Y_CO2_wet']:.2f} %
H2O:   {res['Y_H2O_wet']:.2f} %
N2:    {res['Y_N2_wet']:.2f} %
"""
            if validation_target:
                tgt = validation_target
                val_model_co = res.get('Y_CO_dry', 0.0)
                val_model_h2 = res.get('Y_H2_dry', 0.0)
                val_model_co2 = res.get('Y_CO2_dry', 0.0)
                
                val_paper_co = tgt.get('YCO', 0.0)
                val_paper_h2 = tgt.get('YH2', 0.0)
                val_paper_co2 = tgt.get('YCO2', 0.0)

                output += f"""
-----------------------------------------
      VALIDATION / BENCHMARK (Dry Basis)
-----------------------------------------
Metric       | Model   | Paper | Diff
-------------|---------|------------------|------
Temp (°C)    | {res['TOUT_C']:.1f}  | {tgt.get('TOUT_C', 'N/A')}           | {res['TOUT_C'] - tgt.get('TOUT_C', 0):.1f}
CO (vol%)    | {val_model_co:.1f}    | {val_paper_co}             | {val_model_co - val_paper_co:.1f}
H2 (vol%)    | {val_model_h2:.1f}    | {val_paper_h2}             | {val_model_h2 - val_paper_h2:.1f}
"""
                if val_paper_co2 > 0:
                     output += f"CO2 (vol%)   | {val_model_co2:.1f}    | {val_paper_co2}             | {val_model_co2 - val_paper_co2:.1f}\n"

            self.result_text.insert(tk.END, output)
            
        except Exception as e:
            self.result_text.insert(tk.END, f"\nError: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GasifierApp(root)
    root.mainloop()