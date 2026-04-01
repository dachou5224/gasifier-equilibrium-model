
import numpy as np
from scipy.optimize import root, least_squares
from .thermo_data import get_gibbs_free_energy, get_enthalpy_molar, R_CONST

class StoichiometricSolver:
    """
    Solves gasifier equilibrium using a stoichiometric approach (Temperature Approach).
    System of equations:
    1. Atom balances (C, H, O, N, S)
    2. Equilibrium constants for specific reactions (WGS, Methanation) with Delta_T approach.
    """
    def __init__(self, species_list, atom_matrix):
        self.species_list = species_list
        self.atom_matrix = atom_matrix # Rows: C,H,O,N,S; Cols: Species
        
        # Identify indices for key species
        self.idx_CO = species_list.index('CO')
        self.idx_H2 = species_list.index('H2')
        self.idx_CO2 = species_list.index('CO2')
        self.idx_CH4 = species_list.index('CH4')
        self.idx_H2O = species_list.index('H2O')
        self.idx_N2 = species_list.index('N2')
        self.idx_H2S = species_list.index('H2S')
        self.idx_COS = species_list.index('COS')

    def _calculate_Keq(self, reaction_name, T_K):
        """
        Calculate equilibrium constant Kp for specific reactions at T.
        ln(Kp) = -Delta_G / (RT)
        """
        # 1. Water Gas Shift: CO + H2O <-> CO2 + H2
        if reaction_name == 'WGS':
            try:
                # Delta G = G_products - G_reactants
                G_CO = get_gibbs_free_energy('CO', T_K)
                G_H2O = get_gibbs_free_energy('H2O', T_K)
                G_CO2 = get_gibbs_free_energy('CO2', T_K)
                G_H2 = get_gibbs_free_energy('H2', T_K)
                
                Delta_G = (G_CO2 + G_H2) - (G_CO + G_H2O)
                ln_Kp = -Delta_G / (R_CONST * T_K)
                return np.exp(ln_Kp)
            except Exception as e:
                # Fallback or robust handling
                return 1.0

        # 2. Methanation: CO + 3H2 <-> CH4 + H2O
        elif reaction_name == 'Methanation':
            try:
                G_CO = get_gibbs_free_energy('CO', T_K)
                G_H2 = get_gibbs_free_energy('H2', T_K)
                G_CH4 = get_gibbs_free_energy('CH4', T_K)
                G_H2O = get_gibbs_free_energy('H2O', T_K)
                
                G_H2O = get_gibbs_free_energy('H2O', T_K)
                
                Delta_G = (G_CH4 + G_H2O) - (G_CO + 3*G_H2)
                ln_Kp = -Delta_G / (R_CONST * T_K)
                return np.exp(ln_Kp)
            except Exception:
                return 0.0
        # 3. Boudouard: C + CO2 <-> 2CO
        elif reaction_name == 'Boudouard':
            try:
                G_C = get_gibbs_free_energy('C', T_K)
                G_CO = get_gibbs_free_energy('CO', T_K)
                G_CO2 = get_gibbs_free_energy('CO2', T_K)
                Delta_G = 2 * G_CO - (G_C + G_CO2)
                ln_Kp = -Delta_G / (R_CONST * T_K)
                return np.exp(ln_Kp)
            except Exception:
                return 1.0
        # 4. Steam gasification: C + H2O <-> CO + H2
        elif reaction_name == 'SteamGasification':
            try:
                G_C = get_gibbs_free_energy('C', T_K)
                G_H2O = get_gibbs_free_energy('H2O', T_K)
                G_CO = get_gibbs_free_energy('CO', T_K)
                G_H2 = get_gibbs_free_energy('H2', T_K)
                Delta_G = (G_CO + G_H2) - (G_C + G_H2O)
                ln_Kp = -Delta_G / (R_CONST * T_K)
                return np.exp(ln_Kp)
            except Exception:
                return 1.0
        return 1.0

    def solve(
        self,
        T,
        P_bar,
        atom_input,
        delta_T_wgs=0,
        delta_T_meth=0,
        reaction_set='base',
        char_extent=None,
        carbon_total=None,
        return_meta=False,
    ):
        """
        Solve for equilibrium composition.
        T: Temperature (K)
        P_bar: Pressure (bar)
        atom_input: [n_C, n_H, n_O, n_N, n_S]
        """
        
        # Calculate K values at T + Delta_T
        K_wgs = self._calculate_Keq('WGS', T + delta_T_wgs)
        K_meth = self._calculate_Keq('Methanation', T + delta_T_meth)
        K_boud = self._calculate_Keq('Boudouard', T + delta_T_wgs)
        K_sg = self._calculate_Keq('SteamGasification', T + delta_T_wgs)
        
        # Fixed species
        n_N2 = max(1e-8, atom_input[3] / 2.0)
        
        # S balance -> Assume H2S dominance
        n_S_in = atom_input[4]
        n_COS = max(1e-10, n_S_in * 0.05)
        n_H2S = max(1e-10, n_S_in * 0.95)
        
        # Remaining atoms for C-H-O system
        if carbon_total is None:
            carbon_total = atom_input[0]
        if char_extent is None:
            gas_carbon_target = atom_input[0]
            if carbon_total > 1e-12:
                char_extent = np.clip(gas_carbon_target / carbon_total, 0.0, 1.0)
            else:
                char_extent = 1.0
        else:
            char_extent = np.clip(char_extent, 0.0, 1.0)
            gas_carbon_target = carbon_total * char_extent

        n_C_rem = gas_carbon_target - n_COS
        n_H_rem = atom_input[1] - 2*n_H2S
        n_O_rem = atom_input[2] - n_COS
        
        if n_C_rem <= 0 or n_H_rem <= 0 or n_O_rem <= 0:
            return None

        # Scaling Factors (Approximate magnitudes)
        scale_mol = max(1.0, n_C_rem) 
        
        # Initial guess
        x0 = np.array([
            n_C_rem * 0.60,  # CO
            n_C_rem * 0.30,  # H2
            n_C_rem * 0.05,  # CO2
            n_C_rem * 0.01,  # CH4
            n_C_rem * 0.10   # H2O
        ])
        x0 = np.maximum(x0, 1e-4)

        def base_residuals(vars):
            # Enforce positive moles
            n_CO, n_H2, n_CO2, n_CH4, n_H2O = np.abs(vars)
            
            # 1. Atom Balances (Normalized by input atoms)
            res_C = ((n_CO + n_CO2 + n_CH4) - n_C_rem) / scale_mol
            res_H = ((2*n_H2 + 4*n_CH4 + 2*n_H2O) - n_H_rem) / scale_mol
            res_O = ((n_CO + 2*n_CO2 + n_H2O) - n_O_rem) / scale_mol
            
            # Total moles
            n_tot_cho = n_CO + n_H2 + n_CO2 + n_CH4 + n_H2O
            n_total = n_tot_cho + n_N2 + n_H2S + n_COS
            
            # 4. WGS
            # WGS用对数形式或者归一化形式
            term_wgs_lhs = K_wgs * n_CO * n_H2O
            term_wgs_rhs = n_CO2 * n_H2
            res_wgs = np.log((term_wgs_lhs + 1e-15) / (term_wgs_rhs + 1e-15))
            
            # 5. Methanation
            # 原始形式：
            # K_meth = (n_CH4 * n_H2O / (n_CO * n_H2^3)) * (P / n_total)^-2
            # K_meth * n_CO * n_H2^3 * P^2 = n_CH4 * n_H2O * n_total^2
            # 改用对数形式处理巨大数值跨度问题
            term_meth_lhs = K_meth * n_CO * (n_H2**3) * (P_bar**2)
            term_meth_rhs = n_CH4 * n_H2O * (n_total**2)
            
            # 使用对数差异作为残差
            res_meth = np.log((term_meth_lhs + 1e-15) / (term_meth_rhs + 1e-15))
            
            return [res_C, res_H, res_O, res_wgs, res_meth]

        def extended_char_residuals(vars):
            n_CO, n_H2, n_CO2, n_CH4, n_H2O = np.abs(vars)

            res_C = ((n_CO + n_CO2 + n_CH4) - n_C_rem) / scale_mol
            res_H = ((2*n_H2 + 4*n_CH4 + 2*n_H2O) - n_H_rem) / scale_mol
            res_O = ((n_CO + 2*n_CO2 + n_H2O) - n_O_rem) / scale_mol

            n_tot_cho = n_CO + n_H2 + n_CO2 + n_CH4 + n_H2O
            n_total = n_tot_cho + n_N2 + n_H2S + n_COS

            term_boud_lhs = K_boud * n_CO2 * n_total
            term_boud_rhs = (n_CO**2) * P_bar
            res_boud = np.log((term_boud_lhs + 1e-15) / (term_boud_rhs + 1e-15))

            term_sg_lhs = K_sg * n_H2O * n_total
            term_sg_rhs = n_CO * n_H2 * P_bar
            res_sg = np.log((term_sg_lhs + 1e-15) / (term_sg_rhs + 1e-15))

            term_meth_lhs = K_meth * n_CO * (n_H2**3) * (P_bar**2)
            term_meth_rhs = n_CH4 * n_H2O * (n_total**2)
            res_meth = np.log((term_meth_lhs + 1e-15) / (term_meth_rhs + 1e-15))

            return [res_C, res_H, res_O, res_boud, res_sg, res_meth]

        def char_submodel_residuals(vars):
            n_CO, n_H2, n_CO2, n_CH4, n_H2O = np.abs(vars)

            res_C = ((n_CO + n_CO2 + n_CH4) - n_C_rem) / scale_mol
            res_H = ((2*n_H2 + 4*n_CH4 + 2*n_H2O) - n_H_rem) / scale_mol
            res_O = ((n_CO + 2*n_CO2 + n_H2O) - n_O_rem) / scale_mol

            n_tot_cho = n_CO + n_H2 + n_CO2 + n_CH4 + n_H2O
            n_total = n_tot_cho + n_N2 + n_H2S + n_COS

            # C + CO2 <-> 2CO, solid carbon activity = 1
            term_boud_lhs = K_boud * n_CO2 * n_total
            term_boud_rhs = (n_CO**2) * P_bar
            res_boud = np.log((term_boud_lhs + 1e-15) / (term_boud_rhs + 1e-15))

            # C + H2O <-> CO + H2, solid carbon activity = 1
            term_sg_lhs = K_sg * n_H2O * n_total
            term_sg_rhs = n_CO * n_H2 * P_bar
            res_sg = np.log((term_sg_lhs + 1e-15) / (term_sg_rhs + 1e-15))

            return [res_C, res_H, res_O, res_boud, res_sg]

        if reaction_set == 'extended_char_v1':
            lsq = least_squares(
                extended_char_residuals,
                x0,
                bounds=(1e-12, np.inf),
                method='trf',
                ftol=1e-10,
                xtol=1e-10,
                gtol=1e-10,
            )
            max_res = np.max(np.abs(lsq.fun))
            success = lsq.success and (max_res < 5e-3)
            result_x = lsq.x
        elif reaction_set == 'char_submodel_v2':
            sol = root(char_submodel_residuals, x0, method='lm', options={'ftol': 1e-10})
            max_res = np.max(np.abs(sol.fun))
            success = sol.success and (max_res < 1e-4)

            if not success:
                sol = root(char_submodel_residuals, x0, method='hybr', tol=1e-8)
                max_res = np.max(np.abs(sol.fun))
                success = sol.success and (max_res < 1e-4)
            result_x = sol.x if sol.success else None
        else:
            # Use 'lm' first (Levenberg-Marquardt), robust for efficient least-squares
            sol = root(base_residuals, x0, method='lm', options={'ftol': 1e-10})
            
            # Check convergence quality
            max_res = np.max(np.abs(sol.fun))
            success = sol.success and (max_res < 1e-4)

            if not success:
                # Try 'hybr' (Powell's hybrid method)
                sol = root(base_residuals, x0, method='hybr', tol=1e-8)
                max_res = np.max(np.abs(sol.fun))
                success = sol.success and (max_res < 1e-4)
            result_x = sol.x if sol.success else None
            
        if success:
            n_res = np.abs(result_x)
            final_moles = np.zeros(len(self.species_list))
            final_moles[self.idx_CO] = n_res[0]
            final_moles[self.idx_H2] = n_res[1]
            final_moles[self.idx_CO2] = n_res[2]
            final_moles[self.idx_CH4] = n_res[3]
            final_moles[self.idx_H2O] = n_res[4]
            final_moles[self.idx_N2] = n_N2
            final_moles[self.idx_H2S] = n_H2S
            final_moles[self.idx_COS] = n_COS
            if return_meta:
                return final_moles, {
                    'char_extent': char_extent,
                    'carbon_total': carbon_total,
                    'gas_carbon_target': gas_carbon_target,
                    'residual_carbon_mol': max(0.0, carbon_total - gas_carbon_target),
                }
            return final_moles
        else:
            return None
