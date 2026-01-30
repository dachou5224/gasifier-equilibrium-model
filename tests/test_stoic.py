
import sys
import os
import numpy as np

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
from gasifier.validation_cases import VALIDATION_CASES

def test_stoic_solver():
    print("="*60)
    print("🧪 Testing Stoichiometric Solver (Temperature Approach)")
    print("="*60)
    
    # Load Case 6 (Base)
    case_data = VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]
    
    # Create input valid for Stoic
    inputs = case_data.copy()
    inputs.update({
        'Coal Analysis': VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]["Coal Analysis"],
        'Process Conditions': VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]["Process Conditions"]
    })
    
    # Flatten inputs
    flat_inputs = {}
    for k,v in inputs['Coal Analysis'].items(): flat_inputs[k]=v
    for k,v in inputs['Process Conditions'].items(): flat_inputs[k]=v
    
    # Enable Stoic Solver
    flat_inputs['SolverMethod'] = 'Stoic'
    flat_inputs['DeltaT_WGS'] = 0.0
    flat_inputs['DeltaT_Meth'] = 0.0 # Ideal equilibrium
    
    print("\nRunning Simulation (Delta T = 0)...")
    model = GasifierModel(flat_inputs)
    res = model.run_simulation()
    
    print(f"Result T: {res['TOUT_C']:.2f} C")
    print(f"CO: {res['Y_CO_dry']:.2f}%")
    print(f"H2: {res['Y_H2_dry']:.2f}%")
    print(f"CO2: {res['Y_CO2_dry']:.2f}%")
    print(f"CH4: {res['Y_CH4_dry']:.2f}%")
    
    # Compare with RGibbs (approx)
    expected_T = 1370.0
    diff = abs(res['TOUT_C'] - expected_T)
    if diff < 10.0:
        print(f"✅ Agreement with RGibbs/Ref ({expected_T}C) is good: diff={diff:.2f}C")
    else:
        print(f"⚠️  Result differs from Ref ({expected_T}C): diff={diff:.2f}C")

    # Test shifting equilibrium
    print("\nTesting WGS Shift (Delta T = -200K)...")
    flat_inputs['DeltaT_WGS'] = -200.0
    model2 = GasifierModel(flat_inputs)
    res2 = model2.run_simulation()
    
    print(f"Result T: {res2['TOUT_C']:.2f} C")
    print(f"CO: {res2['Y_CO_dry']:.2f}%")
    print(f"H2: {res2['Y_H2_dry']:.2f}%")
    print(f"CO2: {res2['Y_CO2_dry']:.2f}%")
    
    # Expectation: Lower T for WGS (often exo) -> shifts equilibrium.
    # WGS: CO + H2O -> CO2 + H2 (Exothermic)
    # Lower T -> Higher K -> More products (CO2, H2)
    # Let's see if H2 increased.
    if res2['Y_H2_dry'] > res['Y_H2_dry']:
        print("✅ H2 content increased as expected (Lower WGS T -> shift right).")
    else:
        print(f"❓ H2 content change unexpected: {res['Y_H2_dry']} -> {res2['Y_H2_dry']}")

if __name__ == "__main__":
    test_stoic_solver()
