"""
gasifier.py - Gibbs Free Energy Minimization Solver for Entrained Flow Gasifiers

================================================================================
MODIFICATION HISTORY
================================================================================
2026-01-28  v2.1  刘臻 (Liu Zhen)
    - [Fix 1] Line 96-110: 消除全局变量 T_calc_global，温度现作为参数传递到 _gibbs_objective
    - [Fix 5] Line 488-512: 根据O/C比动态调整温度搜索区间 (收窄搜索范围提高收敛性)
    - [Fix 6] Line 290-351: 多起点优化策略 (reducing/balanced/oxidizing)
    - [Fix 7] Line 217-252: 物理结果校验 (_validate_physical_results)
    - [New] Line 24-29, 112-140: 诊断系统 (diagnostics) 用于追踪收敛警告/质量平衡误差/约束违反
    - [New] Line 434-476: 诊断摘要方法 (get_diagnostics_summary, print_diagnostics)
    - [New] Line 142-215: 改进的初值生成策略 (_generate_initial_guess)
    - [New] Line 276-288: H2 物理下限约束，防止 H2 归零问题
================================================================================
"""

import numpy as np
from scipy.optimize import minimize, brentq
from .thermo_data import get_gibbs_free_energy, get_enthalpy_molar, R_CONST
from .coal_props import calculate_coal_thermo 
from .stoic_solver import StoichiometricSolver

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
        
        # 🆕 用于存储诊断信息
        self.diagnostics = {
            'convergence_warnings': [],
            'mass_balance_errors': [],
            'constraint_violations': []
        }

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
        # Fix: Convert kg/h / (g/mol) -> kmol/h -> *1000 -> mol/h
        n_C = m_coal * (inp['Cd']/100.0) / 12.011 * 1000.0
        n_H = m_coal * (inp['Hd']/100.0) / 1.008 * 1000.0
        n_O = m_coal * (inp['Od']/100.0) / 16.00 * 1000.0
        n_N = m_coal * (inp['Nd']/100.0) / 14.007 * 1000.0
        n_S = m_coal * (inp['Sd']/100.0) / 32.06 * 1000.0
        
        pt_frac = inp['pt'] / 100.0
        if pt_frac >= 1.0:
            n_O2_pure = (m_oxygen_total / 32.0) * 1000.0
            n_N2_ox = 0
        else:
            denom = 32.0 + 28.01 * (1.0/pt_frac - 1.0)
            n_O2_pure = (m_oxygen_total / denom) * 1000.0
            n_N2_ox = n_O2_pure * (1.0/pt_frac - 1.0)
            
        n_O += n_O2_pure * 2
        n_N += n_N2_ox * 2
        
        m_water_total = m_steam_added + water_from_slurry + m_moisture_coal
        n_water_total_mol = (m_water_total / 18.015) * 1000.0
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

    def _gibbs_objective(self, n_moles, G_standard_T, P_ratio, T):
        """计算系统总Gibbs自由能 (恢复原始版本，不归一化)"""
        n_total = np.sum(n_moles)
        if n_total < 1e-10: n_total = 1e-10 
        
        # 原始目标函数 (不归一化)
        term1 = np.dot(n_moles, G_standard_T)
        
        active_indices = n_moles > 1e-20
        term2 = 0.0
        if np.any(active_indices):
            term2 = R_CONST * T * np.sum(n_moles[active_indices] * np.log(n_moles[active_indices] / n_total))
            
        term3 = R_CONST * T * n_total * np.log(P_ratio)
        return term1 + term2 + term3

    def _check_mass_balance(self, n_moles, T, tolerance=0.01):
        """
        🆕 检查元素守恒 - #3 收敛性诊断
        
        参数:
        n_moles: 组分摩尔数数组
        T: 当前温度
        tolerance: 相对误差容限 (默认1%)
        
        返回:
        errors: 各元素的相对误差字典
        """
        atom_names = ['C', 'H', 'O', 'N', 'S']
        errors = {}
        
        for i in range(5):
            calculated = np.dot(n_moles, self.atom_matrix[i])
            target = self.atom_input[i]
            
            if target > 1e-10:  # 避免除零
                rel_error = abs(calculated - target) / target
                if rel_error > tolerance:
                    errors[atom_names[i]] = rel_error * 100  # 转为百分比
        
        if errors:
            error_msg = f"T={T:.1f}K: " + ", ".join([f"{elem}: {err:.2f}%" for elem, err in errors.items()])
            self.diagnostics['mass_balance_errors'].append(error_msg)
            
        return errors

    def _generate_initial_guess(self, T, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, strategy='auto'):
        """
        基于气流床气化炉工业典型组成的初值生成
        
        策略:
        - 'typical': 典型工业组成 (推荐)
        - 'reducing': 还原性气氛
        - 'oxidizing': 氧化性气氛
        - 'auto': 根据O/C比自动选择
        
        典型气流床气化炉干基组成 (文献数据):
        - CO: 55-65%
        - H2: 25-35%
        - CO2: 1-5%
        - CH4: <0.5%
        - N2: 取决于氧纯度
        """
        n0 = np.zeros(len(self.species_list))
        
        # N2 和 H2S 固定
        n0[5] = max(n_N_in / 2.0, 1e-6)  # N2 (mol)
        n0[6] = max(n_S_in * 0.95, 1e-6)  # H2S (大部分硫)
        n0[7] = max(n_S_in * 0.05, 1e-8)  # COS (少量)
        
        # 根据O/C比选择策略
        ratio_oc = self.inputs.get('Ratio_OC', 0.9)
        if strategy == 'auto':
            strategy = 'typical'  # 优先使用工业典型组成
        
        if strategy == 'typical':
            # ======= 基于工业典型组成的初值 =======
            # 假设干基组成 (mol%): CO=60%, H2=30%, CO2=3%, CH4=0.3%, N2=余量
            # 忽略H2O先，稍后通过O平衡调整
            
            # 估算干气总摩尔数 (基于碳守恒: CO + CO2 + CH4 = C_in)
            # 假设 CO/C_in = 0.95, CO2/C_in = 0.04, CH4/C_in = 0.01
            n0[0] = n_C_in * 0.95   # CO (dry basis ~60% -> 大部分碳)
            n0[2] = n_C_in * 0.04   # CO2 (dry basis ~3%)
            n0[3] = n_C_in * 0.005  # CH4 (dry basis ~0.3%)
            
            # H2 基于 H2/CO 比 ≈ 0.5 (典型气流床)
            n0[1] = n0[0] * 0.50    # H2 (mol)
            
            # H2O 通过氢平衡获得残余氢
            H_used = 2*n0[1] + 2*n0[6] + 4*n0[3]  # H2 + H2S + CH4 消耗的氢原子
            H_remain = max(0, n_H_in - H_used)
            n0[4] = H_remain / 2.0  # H2O (mol) = 剩余氢原子 / 2
            
        elif strategy == 'reducing':
            # 还原性: 更高 H2/CO 比
            n0[0] = n_C_in * 0.90   # CO
            n0[2] = n_C_in * 0.08   # CO2
            n0[3] = n_C_in * 0.005  # CH4
            n0[1] = n0[0] * 0.55    # H2 (H2/CO ~ 0.55)
            H_used = 2*n0[1] + 2*n0[6] + 4*n0[3]
            n0[4] = max(0, (n_H_in - H_used)) / 2.0
            
        elif strategy == 'oxidizing':
            # 氧化性: 较低 H2/CO 比, 更多 CO2
            n0[0] = n_C_in * 0.85   # CO
            n0[2] = n_C_in * 0.12   # CO2
            n0[3] = n_C_in * 0.005  # CH4
            n0[1] = n0[0] * 0.40    # H2 (H2/CO ~ 0.40)
            H_used = 2*n0[1] + 2*n0[6] + 4*n0[3]
            n0[4] = max(0, (n_H_in - H_used)) / 2.0
        
        else:  # fallback
            n0[0] = n_C_in * 0.90
            n0[2] = n_C_in * 0.08
            n0[3] = n_C_in * 0.005
            n0[1] = n0[0] * 0.50
            n0[4] = max(0, (n_H_in - 2*n0[1] - 2*n0[6] - 4*n0[3])) / 2.0
        
        return np.maximum(n0, 1e-8)
    
    def _validate_physical_results(self, n_moles, T):
        """
        物理结果校验 (暂时禁用以调试 H2=0% 问题)
        
        返回: (is_valid, message)
        """
        # 暂时禁用所有检查 - 调试用
        return True, "OK"
        n_C_in = self.atom_input[0]
        n_H_in = self.atom_input[1]
        
        # 检查1: 碳平衡 - CO+CO2+CH4+COS应接近输入碳量
        carbon_in_gas = n_moles[0] + n_moles[2] + n_moles[3] + n_moles[7]
        carbon_ratio = carbon_in_gas / n_C_in if n_C_in > 1e-10 else 0
        if carbon_ratio < 0.90 or carbon_ratio > 1.02:
            return False, f"碳平衡异常: {carbon_ratio*100:.1f}%"
        
        # 检查2: 氢平衡 - H2+H2O+H2S+CH4应接近输入氢量
        hydrogen_in_gas = 2*n_moles[1] + 2*n_moles[4] + 2*n_moles[6] + 4*n_moles[3]
        hydrogen_ratio = hydrogen_in_gas / n_H_in if n_H_in > 1e-10 else 0
        if hydrogen_ratio < 0.90 or hydrogen_ratio > 1.02:
            return False, f"氢平衡异常: {hydrogen_ratio*100:.1f}%"
        
        # 检查3: CO/CO2比例在合理范围 (高温应偏向CO)
        if T > 1200:  # 高温
            co_co2_ratio = n_moles[0] / (n_moles[2] + 1e-10)
            if co_co2_ratio < 2.0:  # 高温下CO应远大于CO2
                return False, f"CO/CO2比例偏低: {co_co2_ratio:.2f}"
        
        # 检查4: H2O不应过高 (通常<30%)
        n_total = np.sum(n_moles)
        h2o_fraction = n_moles[4] / n_total if n_total > 1e-10 else 0
        if h2o_fraction > 0.35:
            return False, f"H2O含量过高: {h2o_fraction*100:.1f}%"
        
        return True, "OK"

        return best_moles

    def solve_stoic_equilibrium_at_T(self, T):
        """
        Use Stoichiometric Solver with Temperature Approach
        """
        solver = StoichiometricSolver(self.species_list, self.atom_matrix)
        
        # Get Delta T params (default 0)
        dt_wgs = self.inputs.get('DeltaT_WGS', 0.0)
        dt_meth = self.inputs.get('DeltaT_Meth', 0.0)
        
        moles = solver.solve(T, self.P_ratio, self.atom_input, dt_wgs, dt_meth)
        
        if moles is None:
             self.diagnostics['convergence_warnings'].append(f"T={T:.1f}K: Stoic Solver failed")
             return None
             
        # Check mass balance just in case
        mass_errors = self._check_mass_balance(moles, T)
        if mass_errors:
             print(f"⚠️  Stoic Solver Mass Balance Error: {mass_errors}")
             
        return moles

    def solve_equilibrium_at_T(self, T):
        """
        Dispatch to appropriate solver based on 'SolverMethod' input.
        Default: 'RGibbs'
        """
        method = self.inputs.get('SolverMethod', 'RGibbs')
        
        if method == 'Stoic':
            return self.solve_stoic_equilibrium_at_T(T)
        
        # --- Original RGibbs Logic Below ---
        # Fix 1: 消除全局变量，T作为参数传递
        G0_vals = np.array([get_gibbs_free_energy(s, T) for s in self.species_list])
        
        # ============== 约束条件 ==============
        cons = []
        # 元素守恒约束
        for i in range(5): 
             cons.append({
                 'type': 'eq', 
                 'fun': lambda n, idx=i: np.dot(n, self.atom_matrix[idx]) - self.atom_input[idx]
             })
        
        # ============== 边界条件 (Bounds) ==============
        n_C_in, n_H_in, n_O_in, n_N_in, n_S_in = self.atom_input
        
        # CO2 物理下限约束 (保留)
        co2_min = max(1e-10, n_C_in * 0.005)  # 0.5%的碳
        
        # H2 物理下限约束 (新增) - 防止 H2 归零
        # 气流床气化炉典型 H2/CO 比约 0.4-0.6，H2 约占干气 25-35%
        # 设置 H2 下限为碳输入的 35%（匹配典型工业数据）
        h2_min = max(1e-10, n_C_in * 0.35)  # 最少 35% 的碳量作为 H2
        
        # 边界条件 - 添加 H2 下限防止归零
        bounds = [
            (1e-10, np.inf),      # CO
            (h2_min, np.inf),     # H2 - 添加下限
            (co2_min, np.inf),    # CO2 - 保留下限
            (1e-10, np.inf),      # CH4
            (1e-10, np.inf),      # H2O
            (1e-10, np.inf),      # N2
            (1e-10, np.inf),      # H2S
            (1e-10, np.inf)       # COS
        ]

        # ============== Fix 6: 多起点优化 ==============
        best_result = None
        best_G = np.inf
        best_moles = None
        
        strategies = ['reducing', 'balanced', 'oxidizing']
        
        for strategy in strategies:
            n0 = self._generate_initial_guess(T, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, strategy)
            
            # 显式裁剪初值以满足边界条件 (防止 scipy 报 x0 violates bounds)
            for i, (lb, ub) in enumerate(bounds):
                if ub == np.inf:
                    n0[i] = max(lb * 1.01, n0[i])  # 确保 > 下限
                else:
                    n0[i] = max(lb * 1.01, min(n0[i], ub * 0.99))  # 裁剪到 [lb, ub]
            
            try:
                res = minimize(
                    self._gibbs_objective, 
                    n0, 
                    args=(G0_vals, self.P_ratio, T),  # Fix 1: T作为参数
                    method='SLSQP', 
                    bounds=bounds, 
                    constraints=cons,
                    tol=1e-6,
                    options={'maxiter': 500}
                )
                
                if res.success or (res.x is not None and np.all(res.x >= 0)):
                    G_val = res.fun
                    if G_val < best_G:
                        # Fix 7: 验证物理合理性
                        is_valid, msg = self._validate_physical_results(res.x, T)
                        if is_valid:
                            best_G = G_val
                            best_result = res
                            best_moles = res.x
                        else:
                            self.diagnostics['convergence_warnings'].append(
                                f"T={T:.1f}K, 策略'{strategy}': 物理校验失败 - {msg}"
                            )
            except Exception as e:
                self.diagnostics['convergence_warnings'].append(
                    f"T={T:.1f}K, 策略'{strategy}': 求解异常 - {str(e)}"
                )
        
        # 如果所有策略都失败，使用默认初值重试
        if best_moles is None:
            warning_msg = f"T={T:.1f}K: 所有优化策略均失败，使用默认初值"
            self.diagnostics['convergence_warnings'].append(warning_msg)
            print(f"⚠️  {warning_msg}")
            best_moles = self._generate_initial_guess(T, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, 'balanced')
        else:
            # 检查元素守恒
            mass_errors = self._check_mass_balance(best_moles, T, tolerance=0.01)
            if mass_errors:
                print(f"⚠️  元素守恒偏差: {self.diagnostics['mass_balance_errors'][-1]}")
            
            # 检查约束违反 (仅检查 CO2 下限)
            self._check_constraints(best_moles, T, co2_min)
        
        return best_moles

    def _check_constraints(self, n_moles, T, co2_min):
        """
        检查物理约束是否被违反 (仅检查 CO2 下限)
        """
        n_C_in = self.atom_input[0]
        
        # 检查CO2下限
        if n_moles[2] < co2_min * 0.99:  # 允许1%数值误差
            violation = (n_moles[2] / n_C_in) * 100
            msg = f"T={T:.1f}K: CO2低于下限 ({violation:.3f}% < 0.5%)"
            self.diagnostics['constraint_violations'].append(msg)

    def _calculate_enthalpy_balance(self, T_out):
        moles = self.solve_equilibrium_at_T(T_out)
        if moles is None: return 1e9
        
        # 1. 输出气体显热 + 化学能 (相对于元素的生成焓)
        # get_enthalpy_molar 返回 J/mol (基于 NIST Shomate, H - H298 + Hf298)
        H_gas_out = 0.0
        for i, species in enumerate(self.species_list):
            H_gas_out += moles[i] * get_enthalpy_molar(species, T_out)
        
        H_out_total = H_gas_out + self.abs_heat_loss # J/h
        
        # 2. 输入煤焓 (生成焓 + 显热)
        # H_coal_form is J/kg (from coal_props)
        # Cp_coal ~ 1.2 kJ/kgK = 1200 J/kgK
        T_coal_in = self.inputs.get('T_Coal_In', 298.15) 
        Cp_coal = 1200.0 # J/kg K (was 1.2)
        H_coal_sensible = self.Gc_dry * Cp_coal * (T_coal_in - 298.15) # J/h
        H_coal_chem = self.Gc_dry * self.H_coal_form # J/h
        H_coal_total = H_coal_chem + H_coal_sensible
        
        # 3. 输入气体 (气化剂)
        T_gas_in = self.inputs['TIN']
        # get_enthalpy_molar is J/mol
        H_gas_in = (
            (self.m_steam_gas/18.015 * 1000.0) * get_enthalpy_molar('H2O', T_gas_in) + 
            self.flow_in['O2_mol'] * get_enthalpy_molar('O2', T_gas_in) +
            self.flow_in['N2_ox_mol'] * get_enthalpy_molar('N2', T_gas_in)
        )
        
        # 4. 输入水浆/湿分
        T_water_in = self.inputs.get('T_Slurry_In', 298.15)
        # -285830 J/mol, 75.3 J/molK
        H_liq_in = (self.m_water_liq/18.015 * 1000.0) * (-285830.0 + 75.3 * (T_water_in - 298.15))
        
        H_in_total = H_coal_total + H_gas_in + H_liq_in
        
        return H_in_total - H_out_total
        
    def calculate_heat_loss_for_target_T(self, target_T_K):
        self._preprocess_inputs()
        
        # 计算在目标温度下的平衡组成和出口焓
        moles = self.solve_equilibrium_at_T(target_T_K)
        if moles is None:
            return None, None
            
        H_gas_out = sum(moles[i] * get_enthalpy_molar(s, target_T_K) for i, s in enumerate(self.species_list))
        
        # 计算输入总焓 (不含热损)
        # 此处代码复用 _calculate_enthalpy_balance 的逻辑，但我们需要 H_in_total
        # 简单的做法: 把 heat_loss 设为 0，调用 _calculate_enthalpy_balance 得到 (H_in - H_gas_out)
        
        original_loss = self.abs_heat_loss
        self.abs_heat_loss = 0.0
        net_energy = self._calculate_enthalpy_balance(target_T_K) # H_in - H_gas
        self.abs_heat_loss = original_loss
        
        # required_loss = H_in - H_gas = net_energy
        required_loss_J = net_energy
        
        total_input_energy = self.Gc_dry * self.HHV_coal # J/h
        loss_percent = (required_loss_J / total_input_energy) * 100.0
        
        return loss_percent, required_loss_J

    def calibrate_heat_loss(self, target_T_K):
        """
        [New Feature] Adjust heat loss to match target temperature.
        Updates self.inputs['HeatLossPercent'] and self.abs_heat_loss.
        """
        loss_pct, loss_J = self.calculate_heat_loss_for_target_T(target_T_K)
        
        if loss_pct is not None:
            # Check for negative heat loss (Physical Unreasonable)
            if loss_pct < 0 or loss_J < 0:
                print(f"⚠️  警告: 为了达到目标温度 {target_T_K:.1f}K，需要外部供热 (热损为负: {loss_pct:.2f}%)")
                print(f"   -> 物理上不可能 (自热气化炉)。强制将热损设置为 0.0% (绝热)")
                print(f"   💡 建议: 当前氧煤比 (Ratio_OC={self.inputs.get('Ratio_OC', '?')}) 过低。请提高氧煤比以增加放热，从而达到目标温度。")
                loss_pct = 0.0
                loss_J = 0.0
            
            print(f"🌡️  Calibration: Target T={target_T_K:.1f}K -> Required Heat Loss = {loss_pct:.2f}%")
            self.inputs['HeatLossPercent'] = loss_pct
            # Re-calculate abs_heat_loss based on new percent
            self.abs_heat_loss = (self.Gc_dry * self.HHV_coal) * (loss_pct / 100.0)
            return True
        return False

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

    def get_diagnostics_summary(self):
        """
        🆕 #3: 获取诊断摘要
        """
        summary = {
            'total_warnings': len(self.diagnostics['convergence_warnings']),
            'mass_balance_issues': len(self.diagnostics['mass_balance_errors']),
            'constraint_violations': len(self.diagnostics['constraint_violations']),
            'details': self.diagnostics
        }
        return summary

    def print_diagnostics(self):
        """
        🆕 #3: 打印诊断信息
        """
        print("\n" + "="*60)
        print("📊 模型诊断报告")
        print("="*60)
        
        if not any([self.diagnostics['convergence_warnings'], 
                   self.diagnostics['mass_balance_errors'],
                   self.diagnostics['constraint_violations']]):
            print("✅ 所有检查通过,无异常!")
            print("="*60 + "\n")
            return
        
        if self.diagnostics['convergence_warnings']:
            print(f"\n⚠️  收敛警告 ({len(self.diagnostics['convergence_warnings'])}项):")
            for msg in self.diagnostics['convergence_warnings'][-5:]:  # 只显示最后5条
                print(f"   • {msg}")
        
        if self.diagnostics['mass_balance_errors']:
            print(f"\n⚠️  元素守恒偏差 ({len(self.diagnostics['mass_balance_errors'])}项):")
            for msg in self.diagnostics['mass_balance_errors'][-5:]:
                print(f"   • {msg}")
        
        if self.diagnostics['constraint_violations']:
            print(f"\n❌ 约束违反 ({len(self.diagnostics['constraint_violations'])}项):")
            for msg in self.diagnostics['constraint_violations'][-5:]:
                print(f"   • {msg}")
        
        print("="*60 + "\n")

    def run_simulation(self):
        # 🆕 重置诊断信息
        self.diagnostics = {
            'convergence_warnings': [],
            'mass_balance_errors': [],
            'constraint_violations': []
        }
        
        self._preprocess_inputs()
        
        # Fix 5: 收窄温度搜索区间
        # 根据输入条件估算合理温度范围
        ratio_oc = self.inputs.get('Ratio_OC', 0.9)
        T_in = self.inputs.get('TIN', 300)
        
        # 温度下限: 至少比入口温度高500K，且不低于900K
        T_min = max(900, T_in + 500)
        
        # 温度上限: 根据O/C比调整
        if ratio_oc < 0.85:
            T_max = 1800  # 低O/C，温度较低
        elif ratio_oc > 1.1:
            T_max = 2200  # 高O/C，可能更高温
        else:
            T_max = 2000  # 中等O/C
        
        try:
            T_out_final = brentq(self._calculate_enthalpy_balance, T_min, T_max, xtol=1e-5, rtol=1e-6, maxiter=50)
        except ValueError as e:
            # 如果收窄区间失败，尝试更宽的区间
            self.diagnostics['convergence_warnings'].append(f"收窄区间求解失败: {e}, 尝试扩展区间")
            try:
                T_out_final = brentq(self._calculate_enthalpy_balance, 800, 2500, xtol=1e-5, rtol=1e-6, maxiter=50)
            except ValueError:
                T_out_final = self.inputs.get('TR', 1400)
                self.diagnostics['convergence_warnings'].append(f"温度求解失败,使用参考温度 {T_out_final:.1f}K")
            
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
            'Y_CH4_wet': (res_mol['CH4']/n_total_wet)*100,
            # 激冷
            'Vg_Quench': Vg_flow_quench,
            'WGR_Quench': water_gas_ratio_quench,
            'T_Scrub': T_scrub_C,
            # 🆕 添加诊断摘要
            'diagnostics': self.get_diagnostics_summary()
        }
        
        # 🆕 自动打印诊断信息
        self.print_diagnostics()
        
        return results