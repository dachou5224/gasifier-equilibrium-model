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
            'candidate_failures': [],
            'mass_balance_errors': [],
            'constraint_violations': []
        }
        self.char_state = {
            'char_extent': None,
            'carbon_total_mol': None,
            'gas_carbon_target_mol': None,
            'residual_carbon_mol': None,
        }

    def _apply_total_heat_loss_percent(self, total_loss_percent):
        total_loss_percent = float(total_loss_percent)
        if 'PhysicalHeatLossPercent' in self.inputs or self.inputs.get('HeatLossMode') == 'effective_split_v2':
            physical_pct = float(self.inputs.get('PhysicalHeatLossPercent', 0.0))
            self.inputs['ModelCorrectionPercent'] = total_loss_percent - physical_pct
        self.inputs['HeatLossPercent'] = total_loss_percent

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

        if inp.get('CarbonConversionMode') == 'grouped_default_v1':
            inp['CarbonConversion'] = self._estimate_carbon_conversion()
        if inp.get('DeltaTMode') == 'grouped_default_v2':
            delta_tuning = self._estimate_delta_t_params()
            inp['DeltaT_WGS'] = delta_tuning['DeltaT_WGS']
            inp['DeltaT_Meth'] = delta_tuning['DeltaT_Meth']

        X_c = inp.get('CarbonConversion', 0.99)
        self.n_C_total_in = n_C
        self.char_extent_target = np.clip(X_c, 0.0, 1.0)
        self.n_C_gas_target = self.n_C_total_in * self.char_extent_target
        self.residual_carbon_target = max(0.0, self.n_C_total_in - self.n_C_gas_target)

        self.char_state = {
            'char_extent': self.char_extent_target,
            'carbon_total_mol': self.n_C_total_in,
            'gas_carbon_target_mol': self.n_C_gas_target,
            'residual_carbon_mol': self.residual_carbon_target,
        }
        
        self.atom_input = np.array([self.n_C_gas_target, n_H, n_O, n_N, n_S])
        
        self.flow_in = {
            'Coal_Dry': self.Gc_dry,
            'O2_mol': n_O2_pure,
            'N2_ox_mol': n_N2_ox
        }
        self.m_steam_gas = m_steam_added 
        self.m_water_liq = water_from_slurry + m_moisture_coal

        if inp.get('HeatLossMode') == 'effective_suite_v1':
            inp['HeatLossPercent'] = self._estimate_effective_heat_loss_percent()
            inp.setdefault('PhysicalHeatLossPercent', inp['HeatLossPercent'])
            inp.setdefault('ModelCorrectionPercent', 0.0)
        elif inp.get('HeatLossMode') == 'effective_split_v2':
            components = self._estimate_heat_loss_components()
            inp['PhysicalHeatLossPercent'] = components['physical']
            inp['ModelCorrectionPercent'] = components['correction']
            inp['HeatLossPercent'] = components['total']
        else:
            physical_pct = float(inp.get('PhysicalHeatLossPercent', inp.get('HeatLossPercent', 1.0)))
            correction_pct = float(inp.get('ModelCorrectionPercent', 0.0))
            inp['PhysicalHeatLossPercent'] = physical_pct
            inp['ModelCorrectionPercent'] = correction_pct
            inp['HeatLossPercent'] = physical_pct + correction_pct

        self.abs_heat_loss = (self.Gc_dry * self.HHV_coal) * (inp.get('HeatLossPercent', 1.0) / 100.0)

    def _infer_scale_class(self):
        """
        基于干煤处理量粗分 pilot / industrial。
        这里的热损是“有效热损”，除壁散热外也吸收未建模热汇。
        """
        return 'industrial' if self.Gc_dry >= 5000.0 else 'pilot'

    def _estimate_effective_heat_loss_percent(self):
        """
        按装置尺度与进料型式给出经验有效热损百分比。

        经验依据:
        - pilot 干粉: 约 3%
        - pilot 浆态: 约 2%
        - industrial 干粉: 约 11%
        - industrial 浆态: 约 7%

        这里不是纯壁面散热，而是用于吸收工业实际中未完全建模的热汇
        (辐射、炉衬、熔渣/灰、非理想混合、未建模副反应等)。
        """
        scale_class = self._infer_scale_class()
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')

        if scale_class == 'industrial':
            return 7.0 if gasifier_type == 'CWS' else 11.0
        return 2.0 if gasifier_type == 'CWS' else 3.0

    def _estimate_heat_loss_components(self):
        """
        将总“有效热损”拆为:
        - PhysicalHeatLossPercent: 更接近真实散热/炉衬/外壁热损
        - ModelCorrectionPercent: 用于吸收简化模型遗漏项, 可为负
        """
        scale_class = self._infer_scale_class()
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')

        if scale_class == 'industrial' and gasifier_type == 'Dry Powder':
            physical_pct = 1.5
            correction_pct = 9.5
        elif scale_class == 'industrial' and gasifier_type == 'CWS':
            physical_pct = 1.0
            correction_pct = 9.0
        elif scale_class == 'pilot' and gasifier_type == 'Dry Powder':
            physical_pct = 4.0
            correction_pct = -1.0
        else:
            physical_pct = 2.5
            correction_pct = -0.5

        return {
            'physical': physical_pct,
            'correction': correction_pct,
            'total': physical_pct + correction_pct,
        }

    def _estimate_carbon_conversion(self):
        """
        分组经验值:
        - industrial CWS: 保持略低转化率以改善工业浆态案例
        - 其余工况: 维持接近完全转化
        """
        scale_class = self._infer_scale_class()
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')
        if scale_class == 'industrial' and gasifier_type == 'CWS':
            return 0.99
        return 0.99

    def _estimate_delta_t_params(self):
        """
        分组经验值:
        - industrial CWS: 更接近平衡, 不再人为抬高 WGS 温度修正
        - pilot CWS: 保留较大的 WGS temperature approach
        - dry feed: 默认使用 0
        """
        scale_class = self._infer_scale_class()
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')

        if gasifier_type == 'CWS':
            if scale_class == 'industrial':
                return {'DeltaT_WGS': 0.0, 'DeltaT_Meth': 0.0}
            return {'DeltaT_WGS': 150.0, 'DeltaT_Meth': 0.0}
        return {'DeltaT_WGS': 0.0, 'DeltaT_Meth': 0.0}

    def _estimate_char_extent_from_correlation(self, T):
        """
        经验相关式版本的 char extent:
        当前校准结果表明，最稳定的经验项是一个非常轻的挥发分修正。
        先保守采用:
        - 挥发分越高, char extent 略高
        - 暂不再显式引入 T / O-C / slurry 项, 避免把已稳定的 19 案重新拉坏
        """
        base_extent = float(self.inputs.get('CarbonConversion', self.char_extent_target))
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')
        volatile = float(self.inputs.get('Vd', 0.0))

        volatile_term = 0.00010 * (volatile - 30.0)
        extent = base_extent + volatile_term
        lower = 0.96 if gasifier_type == 'CWS' else 0.97
        upper = 0.999
        return float(np.clip(extent, lower, upper))

    def _update_self_consistent_delta_t(self, T, moles, base_dt_wgs, base_dt_meth):
        """
        基于当前求得的组分结果，对 DeltaT 做一次自洽更新。
        这里不引入完整动力学，只做 lightweight fixed-point 修正：
        - 低温、富蒸汽/富 CO2 时，WGS 偏离平衡更明显 -> DeltaT_WGS 更大
        - 高温、贫蒸汽时，WGS 更接近平衡 -> DeltaT_WGS 更小
        - Methanation 采用更保守的同类缩放
        """
        n_total = max(np.sum(moles), 1e-12)
        y = moles / n_total
        y_co = y[0]
        y_h2 = y[1]
        y_co2 = y[2]
        y_ch4 = y[3]
        y_h2o = y[4]

        temp_c = T - 273.15
        temp_factor = np.clip(1400.0 / max(temp_c, 800.0), 0.65, 1.25)
        wgs_composition_factor = np.clip((y_h2o + y_co2 + 1e-6) / (y_co + y_h2 + 1e-6), 0.60, 1.35)
        meth_composition_factor = np.clip((y_ch4 + y_h2o + 1e-6) / (y_co + y_h2 + 1e-6), 0.50, 1.20)

        return {
            'DeltaT_WGS': base_dt_wgs * temp_factor * wgs_composition_factor,
            'DeltaT_Meth': base_dt_meth * temp_factor * meth_composition_factor,
        }

    def _gibbs_objective(self, n_moles, G_standard_T, P_ratio, T):
        """计算系统总Gibbs自由能 (恢复原始版本，不归一化)"""
        n_total = np.sum(n_moles)
        if n_total < 1e-10: n_total = 1e-10 
        
        # 原始目标函数 (不归一化)
        term1 = np.dot(n_moles, G_standard_T)
        
        # 裁剪以防止在极小值处对数发散
        n_moles_safe = np.maximum(n_moles, 1e-15)
        
        term2 = R_CONST * T * np.sum(n_moles_safe * np.log(n_moles_safe / n_total))
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
        residual_carbon = self.char_state.get('residual_carbon_mol') or 0.0
        
        for i in range(5):
            calculated = np.dot(n_moles, self.atom_matrix[i])
            target = self.atom_input[i]
            if i == 0:
                calculated += residual_carbon
                target = self.n_C_total_in
            
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

    def _get_physical_thresholds(self, T):
        """
        根据进料形态和含水/蒸汽负荷动态设置物理校验阈值。
        """
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')
        ratio_sc = self.inputs.get('Ratio_SC', 0.0)
        slurry_conc = self.inputs.get('SlurryConc', 100.0)

        is_slurry_like = gasifier_type == 'CWS' or slurry_conc < 95.0 or ratio_sc >= 0.35

        co_co2_ratio_min = 2.0 if is_slurry_like else 5.0
        if not is_slurry_like and ratio_sc >= 0.20:
            co_co2_ratio_min = 4.0

        h2o_fraction_max = 0.65 if is_slurry_like else 0.40
        h2_fraction_min = 0.05 if T > 1000 else 0.0

        return {
            'co_co2_ratio_min': co_co2_ratio_min,
            'h2o_fraction_max': h2o_fraction_max,
            'h2_fraction_min': h2_fraction_min,
        }
    
    def _validate_physical_results(self, n_moles, T):
        """
        物理结果校验
        
        返回: (is_valid, message)
        """
        n_C_in = self.atom_input[0]
        residual_carbon = self.char_state.get('residual_carbon_mol') or 0.0
        n_H_in = self.atom_input[1]
        
        # 增加总摩尔数防止除零
        n_total = np.sum(n_moles)
        if n_total < 1e-10:
            return False, "体系物质总量趋近于零"

        # 检查1: 碳平衡 - CO+CO2+CH4+COS应接近输入碳量
        carbon_in_gas = n_moles[0] + n_moles[2] + n_moles[3] + n_moles[7]
        carbon_ratio = (carbon_in_gas + residual_carbon) / self.n_C_total_in if self.n_C_total_in > 1e-10 else 0
        if carbon_ratio < 0.90 or carbon_ratio > 1.02:
            return False, f"碳平衡异常: {carbon_ratio*100:.1f}%"
        
        # 检查2: 氢平衡 - H2+H2O+H2S+CH4应接近输入氢量
        hydrogen_in_gas = 2*n_moles[1] + 2*n_moles[4] + 2*n_moles[6] + 4*n_moles[3]
        hydrogen_ratio = hydrogen_in_gas / n_H_in if n_H_in > 1e-10 else 0
        if hydrogen_ratio < 0.90 or hydrogen_ratio > 1.02:
            return False, f"氢平衡异常: {hydrogen_ratio*100:.1f}%"
        
        thresholds = self._get_physical_thresholds(T)

        # 检查3: CO/CO2比例在合理范围 (高温应偏向CO)
        if T > 1200:  # 高温
            co_co2_ratio = n_moles[0] / max(n_moles[2], 1e-10)
            if co_co2_ratio < thresholds['co_co2_ratio_min']:
                return False, f"高温下CO/CO2比例偏低: {co_co2_ratio:.2f}"
                
        # 新增检查: 判断是否有极端的组分归零
        if thresholds['h2_fraction_min'] > 0 and n_moles[1] / n_total < thresholds['h2_fraction_min']:
            return False, f"H2 含量过低: {n_moles[1]/n_total*100:.1f}%"
        
        # 检查4: H2O不应过高
        h2o_fraction = n_moles[4] / n_total
        if h2o_fraction > thresholds['h2o_fraction_max']:
            return False, f"H2O含量过高: {h2o_fraction*100:.1f}%"
        
        return True, "OK"

    def solve_stoic_equilibrium_at_T(self, T):
        """
        Use Stoichiometric Solver with Temperature Approach
        """
        solver = StoichiometricSolver(self.species_list, self.atom_matrix)
        
        # Get Delta T params (default 0)
        dt_wgs = self.inputs.get('DeltaT_WGS', 0.0)
        dt_meth = self.inputs.get('DeltaT_Meth', 0.0)
        reaction_set = self.inputs.get('StoicReactionSet', 'base')
        char_extent = None
        carbon_total = None
        return_meta = False
        if self.inputs.get('CharExtentMode') == 'explicit_v1':
            char_extent = self.char_extent_target
            carbon_total = self.n_C_total_in
            return_meta = True
        elif self.inputs.get('CharExtentMode') == 'correlation_v2':
            char_extent = self._estimate_char_extent_from_correlation(T)
            carbon_total = self.n_C_total_in
            return_meta = True

        if self.inputs.get('DeltaTMode') == 'grouped_self_consistent_v3':
            current_dt_wgs = dt_wgs
            current_dt_meth = dt_meth
            moles = None
            for _ in range(5):
                solved = solver.solve(
                    T, self.P_ratio, self.atom_input, current_dt_wgs, current_dt_meth, reaction_set,
                    char_extent=char_extent, carbon_total=carbon_total, return_meta=return_meta
                )
                if return_meta and solved is not None:
                    moles, meta = solved
                    self.char_state.update(meta)
                else:
                    moles = solved
                if moles is None:
                    break
                updated = self._update_self_consistent_delta_t(T, moles, dt_wgs, dt_meth)
                new_dt_wgs = 0.5 * current_dt_wgs + 0.5 * updated['DeltaT_WGS']
                new_dt_meth = 0.5 * current_dt_meth + 0.5 * updated['DeltaT_Meth']
                if abs(new_dt_wgs - current_dt_wgs) < 1e-3 and abs(new_dt_meth - current_dt_meth) < 1e-3:
                    current_dt_wgs = new_dt_wgs
                    current_dt_meth = new_dt_meth
                    break
                current_dt_wgs = new_dt_wgs
                current_dt_meth = new_dt_meth
            self.inputs['DeltaT_WGS_Effective'] = current_dt_wgs
            self.inputs['DeltaT_Meth_Effective'] = current_dt_meth
        else:
            solved = solver.solve(
                T, self.P_ratio, self.atom_input, dt_wgs, dt_meth, reaction_set,
                char_extent=char_extent, carbon_total=carbon_total, return_meta=return_meta
            )
            if return_meta and solved is not None:
                moles, meta = solved
                self.char_state.update(meta)
            else:
                moles = solved
            self.inputs['DeltaT_WGS_Effective'] = dt_wgs
            self.inputs['DeltaT_Meth_Effective'] = dt_meth
        
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
            stoic_moles = self.solve_stoic_equilibrium_at_T(T)
            if stoic_moles is not None:
                return stoic_moles
            self.diagnostics['convergence_warnings'].append(
                f"T={T:.1f}K: Stoic Solver failed, fallback to RGibbs"
            )
        
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
        
        # 边界条件 - 移除人工 H2 下限，统一使用数值最低值，让 Gibbs 最小化去寻找
        bounds = [(1e-10, np.inf) for _ in range(8)]
        bounds[2] = (co2_min, np.inf) # 保留 CO2 最低物理限制防止除零等

        # ============== Fix 6: 多求解器与多起点优化 ==============
        best_result = None
        best_G = np.inf
        best_moles = None
        candidate_failures = []
        
        # 扩展初值生成策略，包括利用 stoic_solver 预估
        strategies = ['stoic_based', 'typical', 'reducing', 'oxidizing']
        
        # 如果可以使用 Stoic pre-solving
        stoic_guess = None
        try:
            stoic_moles = self.solve_stoic_equilibrium_at_T(T)
            if stoic_moles is not None:
                stoic_guess = stoic_moles
        except Exception:
            pass
        
        # 两个求解器交替尝试
        methods_to_try = [('trust-constr', {'maxiter': 1000, 'xtol': 1e-5, 'gtol': 1e-5}),
                          ('SLSQP', {'maxiter': 500, 'ftol': 1e-6})]

        for strategy in strategies:
            if strategy == 'stoic_based':
                if stoic_guess is not None:
                    n0 = stoic_guess.copy()
                else:
                    continue
            else:
                n0 = self._generate_initial_guess(T, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, strategy)
            
            # 显式裁剪初值以满足边界条件，避免 trust-constr 报错 "x0 violates bound constraints"
            for i, (lb, ub) in enumerate(bounds):
                margin = 1e-8  # 略微大于边界以满足强不等式约束要求
                if ub == np.inf:
                    n0[i] = max(lb + margin, n0[i])
                else:
                    n0[i] = max(lb + margin, min(n0[i], ub - margin))
            
            # 尝试不同的优化算法
            for method_name, options in methods_to_try:
                try:
                    from scipy.optimize import Bounds
                    # 对于 trust-constr，必须提供 Bounds 对象
                    scipy_bounds = Bounds([b[0] for b in bounds], [b[1] for b in bounds], keep_feasible=True)
                    
                    if method_name == 'trust-constr':
                        # trust-constr 对线性约束有更好的内部处理
                        from scipy.optimize import LinearConstraint
                        # cons_matrix @ x = cons_target
                        cons_matrix = np.zeros((5, 8))
                        cons_target = np.zeros(5)
                        for i in range(5):
                            cons_matrix[i, :] = self.atom_matrix[i]
                            cons_target[i] = self.atom_input[i]
                        scipy_cons = LinearConstraint(cons_matrix, cons_target - 1e-5, cons_target + 1e-5)
                        
                        res = minimize(
                            self._gibbs_objective, 
                            n0, 
                            args=(G0_vals, self.P_ratio, T),
                            method='trust-constr', 
                            bounds=scipy_bounds, 
                            constraints=scipy_cons,
                            options=options
                        )
                    else:
                        res = minimize(
                            self._gibbs_objective, 
                            n0, 
                            args=(G0_vals, self.P_ratio, T), 
                            method='SLSQP', 
                            bounds=bounds, 
                            constraints=cons,
                            options=options
                        )
                    
                    if res.success or (res.x is not None and np.all(res.x >= 0)):
                        # 检查约束满足情况，trust-constr有一定宽容度
                        mass_errs = self._check_mass_balance(res.x, T, tolerance=0.02)
                        if not mass_errs: # 如果满足元素守恒
                            G_val = res.fun
                            # 在此处就直接过滤极高能量的无意义解
                            if G_val < best_G:
                                is_valid, msg = self._validate_physical_results(res.x, T)
                                if is_valid:
                                    best_G = G_val
                                    best_result = res
                                    best_moles = res.x
                                else:
                                    candidate_failures.append(
                                        f"T={T:.1f}K, 策略'{strategy}', 优化器'{method_name}': 物理校验失败 - {msg}"
                                    )
                except Exception as e:
                    candidate_failures.append(
                        f"T={T:.1f}K, 策略'{strategy}', 优化器'{method_name}': 求解异常 - {str(e)}"
                    )
        
        # 如果所有策略都失败，使用默认初值重试或容忍较好的无效解
        if best_moles is None:
            warning_msg = f"T={T:.1f}K: 所有优化策略均失败或未通过物理校验，使用平衡生成初值"
            self.diagnostics['convergence_warnings'].append(warning_msg)
            self.diagnostics['candidate_failures'].extend(candidate_failures)
            print(f"⚠️  {warning_msg}")
            if stoic_guess is not None:
                best_moles = stoic_guess
            else:
                best_moles = self._generate_initial_guess(T, n_C_in, n_H_in, n_O_in, n_N_in, n_S_in, 'balanced')
        else:
            if candidate_failures:
                self.diagnostics['candidate_failures'].extend(candidate_failures)
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
            print(f"🌡️  Calibration: Target T={target_T_K:.1f}K -> Required Heat Loss = {loss_pct:.2f}%")
            if 'PhysicalHeatLossPercent' in self.inputs or self.inputs.get('HeatLossMode') == 'effective_split_v2':
                if loss_pct < 0 or loss_J < 0:
                    print("ℹ️  采用 split 模式: 保留非负物理热损, 将缺失热量记入负的模型修正项。")
                self.inputs['HeatLossMode'] = 'manual_split'
                self._apply_total_heat_loss_percent(loss_pct)
            else:
                # 旧模式下 HeatLossPercent 仍被视为纯物理热损, 不允许为负
                if loss_pct < 0 or loss_J < 0:
                    print(f"⚠️  警告: 为了达到目标温度 {target_T_K:.1f}K，需要外部供热 (热损为负: {loss_pct:.2f}%)")
                    print("   -> 非 split 模式下将热损强制设为 0.0%。")
                    loss_pct = 0.0
                    loss_J = 0.0
                self.inputs['HeatLossMode'] = 'manual'
                self._apply_total_heat_loss_percent(loss_pct)
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
                   self.diagnostics['candidate_failures'],
                   self.diagnostics['mass_balance_errors'],
                   self.diagnostics['constraint_violations']]):
            print("✅ 所有检查通过,无异常!")
            print("="*60 + "\n")
            return
        
        if self.diagnostics['convergence_warnings']:
            print(f"\n⚠️  收敛警告 ({len(self.diagnostics['convergence_warnings'])}项):")
            for msg in self.diagnostics['convergence_warnings'][-5:]:  # 只显示最后5条
                print(f"   • {msg}")

        if self.diagnostics['candidate_failures']:
            print(f"\nℹ️  候选解淘汰 ({len(self.diagnostics['candidate_failures'])}项，不计入最终收敛评分):")
            for msg in self.diagnostics['candidate_failures'][-5:]:
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

    def _determine_temperature_bounds(self):
        ratio_oc = self.inputs.get('Ratio_OC', 0.9)
        Tin = self.inputs.get('TIN', 300)
        gasifier_type = self.inputs.get('GasifierType', 'Dry Powder')
        Tmin = max(850, Tin + 450)
        if ratio_oc < 0.8:
            Tmax = 1800
        elif ratio_oc > 1.4:
            Tmax = 2350
        elif ratio_oc > 1.1:
            Tmax = 2200
        else:
            Tmax = 2050
        if gasifier_type == 'CWS' and ratio_oc >= 1.0:
            Tmax = max(Tmax, 2200)
        return Tmin, Tmax

    def run_simulation(self):
        # 🆕 重置诊断信息
        self.diagnostics = {
            'convergence_warnings': [],
            'candidate_failures': [],
            'mass_balance_errors': [],
            'constraint_violations': []
        }
        self.char_state = {
            'char_extent': self.char_extent_target if hasattr(self, 'char_extent_target') else None,
            'carbon_total_mol': getattr(self, 'n_C_total_in', None),
            'gas_carbon_target_mol': getattr(self, 'n_C_gas_target', None),
            'residual_carbon_mol': getattr(self, 'residual_carbon_target', None),
        }

        self._preprocess_inputs()

        T_min, T_max = self._determine_temperature_bounds()

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
        residual_carbon = self.char_state.get('residual_carbon_mol') or 0.0
        err_C = (self.n_C_total_in - (C_out + residual_carbon)) / self.n_C_total_in * 100 if self.n_C_total_in > 1e-12 else 0.0
        
        T_scrub_C = self.inputs.get('T_Scrubber', 210.0)
        T_scrub_K = T_scrub_C + 273.15
        y_H2O_sat = self._calculate_water_saturation(T_scrub_K, self.P)
        n_wet_sat = n_total_dry / (1.0 - y_H2O_sat)
        n_H2O_sat = n_wet_sat * y_H2O_sat
        Vg_flow_quench = n_wet_sat * 22.414
        water_gas_ratio_quench = n_H2O_sat / n_total_dry
        tout_c = T_out_final - 273.15
        t_flag = ''
        if tout_c >= 1900:
            t_flag = 'HIGH'
        elif tout_c <= 1000:
            t_flag = 'LOW'

        results = {
            'TOUT_K': T_out_final,
            'TOUT_C': tout_c,
            'T_flag': t_flag,
            'Vg_wet': Vg_flow_wet,
            'Vg_dry': Vg_flow_dry,
            'HHV': self.HHV_coal,
            'Method': self.hhv_method_used,
            'Heat_Err_Pct': heat_error_percent,
            'HeatLossPercent': self.inputs.get('HeatLossPercent'),
            'PhysicalHeatLossPercent': self.inputs.get('PhysicalHeatLossPercent'),
            'ModelCorrectionPercent': self.inputs.get('ModelCorrectionPercent'),
            'CarbonConversion': self.inputs.get('CarbonConversion'),
            'CharExtent': self.char_state.get('char_extent'),
            'GasCarbonFraction': (C_out / self.n_C_total_in) if self.n_C_total_in > 1e-12 else 0.0,
            'ResidualCarbonMol': residual_carbon,
            'DeltaT_WGS_Effective': self.inputs.get('DeltaT_WGS_Effective'),
            'DeltaT_Meth_Effective': self.inputs.get('DeltaT_Meth_Effective'),
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
