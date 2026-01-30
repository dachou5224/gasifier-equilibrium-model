
import numpy as np
from scipy.optimize import root
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
        return 1.0

    def solve(self, T, P_bar, atom_input, delta_T_wgs=0, delta_T_meth=0):
        """
        Solve for equilibrium composition.
        T: Temperature (K)
        P_bar: Pressure (bar)
        atom_input: [n_C, n_H, n_O, n_N, n_S]
        """
        
        # Calculate K values at T + Delta_T
        K_wgs = self._calculate_Keq('WGS', T + delta_T_wgs)
        K_meth = self._calculate_Keq('Methanation', T + delta_T_meth)
        
        # Fixed species
        n_N2 = max(1e-8, atom_input[3] / 2.0)
        
        # S balance -> Assume H2S dominance
        n_S_in = atom_input[4]
        n_COS = max(1e-10, n_S_in * 0.05)
        n_H2S = max(1e-10, n_S_in * 0.95)
        
        # Remaining atoms for C-H-O system
        n_C_rem = atom_input[0] - n_COS
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

        def residuals(vars):
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
            # K_wgs = (n_CO2 * n_H2) / (n_CO * n_H2O)
            # Linearized form: K * CO * H2O - CO2 * H2 = 0
            # Scale by scale_mol^2
            term_wgs = (K_wgs * n_CO * n_H2O - n_CO2 * n_H2) / (scale_mol**2)
            
            # 5. Methanation
            # K_meth = (n_CH4 * n_H2O / (n_CO * n_H2^3)) * (P / n_total)^-2
            # K * CO * H2^3 * P^2 - CH4 * H2O * n_total^2 = 0
            # Scale? LHS is approx K * M * M^3 * P^2. RHS is M * M * M^2 = M^4.
            # Divide by (scale_mol^4)
            term_meth_lhs = K_meth * n_CO * (n_H2**3) * (P_bar**2)
            term_meth_rhs = n_CH4 * n_H2O * (n_total**2)
            
            # Additional scaling for Methanation (often huge numbers)
            # If K is very small, LHS is small. RHS dominates.
            # If K is large, LHS dominates.
            norm_factor = (scale_mol**4) * max(1.0, P_bar**2) 
            res_meth = (term_meth_lhs - term_meth_rhs) / norm_factor
            
            return [res_C, res_H, res_O, term_wgs, res_meth]

        # Use 'lm' first (Levenberg-Marquardt), robust for efficient least-squares
        sol = root(residuals, x0, method='lm', options={'ftol': 1e-10})
        
        # Check convergence quality
        max_res = np.max(np.abs(sol.fun))
        success = sol.success and (max_res < 1e-4)

        if not success:
            # Try 'hybr' (Powell's hybrid method)
            sol = root(residuals, x0, method='hybr', tol=1e-8)
            max_res = np.max(np.abs(sol.fun))
            success = sol.success and (max_res < 1e-4)
            
        if success:
            n_res = np.abs(sol.x)
            final_moles = np.zeros(len(self.species_list))
            final_moles[self.idx_CO] = n_res[0]
            final_moles[self.idx_H2] = n_res[1]
            final_moles[self.idx_CO2] = n_res[2]
            final_moles[self.idx_CH4] = n_res[3]
            final_moles[self.idx_H2O] = n_res[4]
            final_moles[self.idx_N2] = n_N2
            final_moles[self.idx_H2S] = n_H2S
            final_moles[self.idx_COS] = n_COS
            return final_moles
        else:
            return None
