import numpy as np
from scipy.optimize import minimize, brentq
from thermo_data import get_gibbs_free_energy, get_enthalpy_molar, R_CONST
from coal_props import calculate_coal_thermo 

class GasifierModel:
    def __init__(self, inputs):
        self.inputs = inputs
        self.P = inputs['P']
        self.P_ratio = self.P / 0.1 # bar

        # Index: 0:CO, 1:H2, 2:CO2, 3:CH4, 4:H2O, 5:N2, 6:H2S, 7:COS
        self.species_list = ['CO', 'H2', 'CO2', 'CH4', 'H2O', 'N2', 'H2S', 'COS'] 
        
        self.atom_matrix = np.array([
            # CO, H2, CO2, CH4, H2O, N2, H2S, COS
            [1,   0,  1,   1,   0,   0,  0,   1], # C
            [0,   2,  0,   4,   2,   0,  2,   0], # H
            [1,   0,  2,   0,   1,   0,  0,   1], # O
            [0,   0,  0,   0,   0,   2,  0,   0], # N
            [0,   0,  0,   0,   0,   0,  1,   1]  # S
        ])

    def _preprocess_inputs(self):
        inp = self.inputs
        
        gasifier_type = inp.get('GasifierType', 'Dry Powder')
        if gasifier_type == 'CWS':
            g_slurry = inp['FeedRate'] 
            conc = inp['SlurryConc'] / 100.0
            self.Gc_dry = g_slurry * conc 
            water_from_slurry = g_slurry * (1 - conc)
        else:
            self.Gc_dry = inp['FeedRate']
            water_from_slurry = 0.0

        coal_data_subset = {k: v for k,v in inp.items() if k in ['Cd','Hd','Od','Nd','Sd','Ad','Vd','FCd','HHV_Input']}
        use_formula = True if inp.get('HHV_Method', 0) == 1 else False
        coal_props = calculate_coal_thermo(coal_data_subset, use_formula=use_formula)
        self.HHV_coal = coal_props['HHV']
        self.H_coal_form = coal_props['H_formation']
        self.hhv_method_used = coal_props['Method']

        ratio_oc = inp['Ratio_OC']
        m_oxygen_total = self.Gc_dry * ratio_oc 
        ratio_sc = inp['Ratio_SC']
        m_steam_added = self.Gc_dry * ratio_sc 
        m_moisture_coal = self.Gc_dry * (inp['Mt'] / (100 - inp['Mt']))
        
        m_coal = self.Gc_dry
        n_C = m_coal * (inp['Cd']/100.0) / 12.011
        n_H = m_coal * (inp['Hd']/100.0) / 1.008
        n_O = m_coal * (inp['Od']/100.0) / 16.00
        n_N = m_coal * (inp['Nd']/100.0) / 14.007
        n_S = m_coal * (inp['Sd']/100.0) / 32.06
        
        pt_frac = inp['pt'] / 100.0
        if pt_frac >= 1.0:
            n_O2_pure = m_oxygen_total / 32.0
            n_N2_ox = 0
        else:
            denom = 32.0 + 28.01 * (1.0/pt_frac - 1.0)
            n_O2_pure = m_oxygen_total / denom
            n_N2_ox = n_O2_pure * (1.0/pt_frac - 1.0)
            
        n_O += n_O2_pure * 2
        n_N += n_N2_ox * 2
        
        m_water_total = m_steam_added + water_from_slurry + m_moisture_coal
        n_water_total_mol = m_water_total / 18.015
        n_H += n_water_total_mol * 2
        n_O += n_water_total_mol

        X_c = 0.99
        n_C_gas = n_C * X_c
        
        self.atom_input = np.array([n_C_gas, n_H, n_O, n_N, n_S])
        
        self.flow_in = {
            'Coal_Dry': self.Gc_dry,
            'O2_mol': n_O2_pure,
            'N2_ox_mol': n_N2_ox
        }
        self.m_steam_gas = m_steam_added 
        self.m_water_liq = water_from_slurry + m_moisture_coal
        
        self.abs_heat_loss = (self.Gc_dry * self.HHV_coal) * (inp.get('HeatLossPercent', 1.0) / 100.0)

    def _gibbs_objective(self, n_moles, G_standard_T, P_ratio):
        n_total = np.sum(n_moles)
        if n_total < 1e-10: n_total = 1e-10 
        
        term1 = np.dot(n_moles, G_standard_T)
        
        active_indices = n_moles > 1e-20
        term2 = 0.0
        if np.any(active_indices):
            term2 = R_CONST * T_calc_global * np.sum(n_moles[active_indices] * np.log(n_moles[active_indices] / n_total))
            
        term3 = R_CONST * T_calc_global * n_total * np.log(P_ratio)
        return term1 + term2 + term3

    def solve_equilibrium_at_T(self, T):
        global T_calc_global 
        T_calc_global = T
        
        G0_vals = np.array([get_gibbs_free_energy(s, T) for s in self.species_list])
        
        cons = []
        for i in range(5): 
             cons.append({
                 'type': 'eq', 
                 'fun': lambda n, idx=i: np.dot(n, self.atom_matrix[idx]) - self.atom_input[idx]
             })
             
        n_C_in, n_H_in, n_O_in, n_N_in, n_S_in = self.atom_input
        ch4_limit = n_C_in * 0.005 
        
        bounds = []
        for i, species in enumerate(self.species_list):
            if species == 'CH4':
                bounds.append((1e-10, ch4_limit))
            else:
                bounds.append((1e-10, np.inf))

        n0 = np.zeros(len(self.species_list))
        n0[5] = max(n_N_in / 2.0, 1e-3)
        n0[6] = max(n_S_in, 1e-3)
        n0[0] = n_C_in * 0.90
        n0[2] = n_C_in * 0.10
        H_remain = max(0, n_H_in - 2*n0[6])
        n0[1] = (H_remain * 0.8) / 2.0
        n0[4] = (H_remain * 0.2) / 2.0
        n0[3] = 1e-4
        n0[7] = 1e-4
        n0 = np.maximum(n0, 1e-4)
        
        try:
            res = minimize(
                self._gibbs_objective, 
                n0, 
                args=(G0_vals, self.P_ratio), 
                method='SLSQP', 
                bounds=bounds, 
                constraints=cons,
                tol=1e-5,
                options={'maxiter': 500}
            )
            return res.x if res.success or res.x is not None else n0
        except Exception:
            return n0

    def _calculate_enthalpy_balance(self, T_out):
        moles = self.solve_equilibrium_at_T(T_out)
        if moles is None: return 1e9
        
        H_gas_out = 0.0
        for i, species in enumerate(self.species_list):
            H_gas_out += moles[i] * get_enthalpy_molar(species, T_out)
        H_out_total = H_gas_out + self.abs_heat_loss
        
        T_coal_in = self.inputs.get('T_Coal_In', 298.15) 
        Cp_coal = 1.2
        H_coal_total = self.Gc_dry * self.H_coal_form + self.Gc_dry * Cp_coal * (T_coal_in - 298.15)
        
        T_gas_in = self.inputs['TIN']
        H_gas_in = (
            (self.m_steam_gas/18.015) * get_enthalpy_molar('H2O', T_gas_in) + 
            self.flow_in['O2_mol'] * get_enthalpy_molar('O2', T_gas_in) +
            self.flow_in['N2_ox_mol'] * get_enthalpy_molar('N2', T_gas_in)
        )
        
        T_water_in = self.inputs.get('T_Slurry_In', 298.15)
        H_liq_in = (self.m_water_liq/18.015) * (-285830.0 + 75.3 * (T_water_in - 298.15))
        
        H_in_total = H_coal_total + H_gas_in + H_liq_in
        return H_in_total - H_out_total
        
    def calculate_heat_loss_for_target_T(self, target_T_K):
        self._preprocess_inputs()
        moles = self.solve_equilibrium_at_T(target_T_K)
        H_gas_out = sum(moles[i] * get_enthalpy_molar(s, target_T_K) for i, s in enumerate(self.species_list))
        
        real_loss = self.abs_heat_loss
        self.abs_heat_loss = 0
        balance_val = self._calculate_enthalpy_balance(target_T_K) 
        self.abs_heat_loss = real_loss
        
        required_loss_J = balance_val
        total_input = self.Gc_dry * self.HHV_coal
        return (required_loss_J / total_input) * 100.0, required_loss_J

    def calculate_oxygen_ratio_for_target_T(self, target_T_K, fixed_loss_percent=1.0):
        target_loss_pct = fixed_loss_percent
        def energy_residual(ratio_oc_guess):
            self.inputs['Ratio_OC'] = ratio_oc_guess
            self._preprocess_inputs()
            self.abs_heat_loss = (self.Gc_dry * self.HHV_coal) * (target_loss_pct / 100.0)
            return self._calculate_enthalpy_balance(target_T_K)
        try:
            return brentq(energy_residual, 0.3, 2.0, xtol=1e-4)
        except ValueError:
            raise ValueError("Optimization for O/C ratio failed.")

    def _calculate_water_saturation(self, T_K, P_MPa):
        A = 3.55959
        B = 643.748
        C = -198.043
        try:
            log_p = A - B / (T_K + C)
            P_sat_bar = 10**log_p
        except:
            P_sat_bar = 100.0 
        P_sys_bar = P_MPa * 10.0
        if P_sat_bar >= P_sys_bar:
            y_H2O = 0.95
        else:
            y_H2O = P_sat_bar / P_sys_bar
        return y_H2O

    def run_simulation(self):
        self._preprocess_inputs()
        try:
            T_out_final = brentq(self._calculate_enthalpy_balance, 500, 3500, xtol=1e-5, rtol=1e-6, maxiter=50)
        except ValueError:
            T_out_final = self.inputs['TR']
            
        moles_final = self.solve_equilibrium_at_T(T_out_final)
        
        res_mol = {s: moles_final[i] for i, s in enumerate(self.species_list)}
        
        n_total_wet = np.sum(moles_final)
        n_H2O = res_mol['H2O']
        n_total_dry = n_total_wet - n_H2O
        if n_total_dry < 1e-5: n_total_dry = 1e-5
        
        Vg_flow_wet = n_total_wet * 22.414 
        Vg_flow_dry = n_total_dry * 22.414
        
        heat_error_val = self._calculate_enthalpy_balance(T_out_final)
        heat_error_percent = (heat_error_val / (self.Gc_dry * self.HHV_coal)) * 100
        C_out = res_mol['CO'] + res_mol['CO2'] + res_mol['CH4'] + res_mol['COS']
        err_C = (self.atom_input[0] - C_out)/self.atom_input[0]*100
        
        T_scrub_C = self.inputs.get('T_Scrubber', 210.0)
        T_scrub_K = T_scrub_C + 273.15
        y_H2O_sat = self._calculate_water_saturation(T_scrub_K, self.P)
        n_wet_sat = n_total_dry / (1.0 - y_H2O_sat)
        n_H2O_sat = n_wet_sat * y_H2O_sat
        Vg_flow_quench = n_wet_sat * 22.414
        water_gas_ratio_quench = n_H2O_sat / n_total_dry

        results = {
            'TOUT_K': T_out_final,
            'TOUT_C': T_out_final - 273.15,
            'Vg_wet': Vg_flow_wet,
            'Vg_dry': Vg_flow_dry,
            'HHV': self.HHV_coal,
            'Method': self.hhv_method_used,
            'Heat_Err_Pct': heat_error_percent,
            'ERR_C': err_C,
            # 干基组成
            'Y_CO_dry': (res_mol['CO']/n_total_dry)*100,
            'Y_H2_dry': (res_mol['H2']/n_total_dry)*100,
            'Y_CO2_dry': (res_mol['CO2']/n_total_dry)*100,
            'Y_CH4_dry': (res_mol['CH4']/n_total_dry)*100,
            'Y_N2_dry': (res_mol['N2']/n_total_dry)*100,
            # 湿基组成
            'Y_H2O_wet': (res_mol['H2O']/n_total_wet)*100,
            'Y_CO_wet': (res_mol['CO']/n_total_wet)*100,
            'Y_H2_wet': (res_mol['H2']/n_total_wet)*100,
            'Y_CO2_wet': (res_mol['CO2']/n_total_wet)*100,
            'Y_N2_wet': (res_mol['N2']/n_total_wet)*100,
            'Y_CH4_wet': (res_mol['CH4']/n_total_wet)*100, # [FIXED] 补上了这个键
            # 激冷
            'Vg_Quench': Vg_flow_quench,
            'WGR_Quench': water_gas_ratio_quench,
            'T_Scrub': T_scrub_C
        }
        return results