
import sys
import os
import numpy as np
import matplotlib.pyplot as plt

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gasifier.gasifier import GasifierModel
from gasifier.validation_cases import VALIDATION_CASES

def run_sensitivity():
    print("="*60)
    print("📈 O/C Ratio Sensitivity Analysis (Target T = 1370°C)")
    print("="*60)
    
    # Load Case 6 (Base)
    base_data = VALIDATION_CASES["Paper_Case_6 (Base)"]["inputs"]
    
    # Flatten inputs
    inputs = {}
    for k,v in base_data['Coal Analysis'].items(): inputs[k]=v
    for k,v in base_data['Process Conditions'].items(): inputs[k]=v
    
    # Use Stoic solver by default as it's our new standard
    inputs['SolverMethod'] = 'Stoic'
    inputs['DeltaT_WGS'] = 0.0
    inputs['DeltaT_Meth'] = 0.0
    
    current_oc = inputs['Ratio_OC']
    print(f"Base Case O/C: {current_oc}")
    
    ratios = np.linspace(0.8, 1.2, 20)
    temps = []
    
    print(f"{'O/C Ratio':<10} | {'Temp (C)':<10} | {'Diff (C)':<10}")
    print("-" * 35)
    
    target_T = 1370.0
    best_oc = None
    min_diff = 1000.0
    
    for r in ratios:
        inputs['Ratio_OC'] = r
        model = GasifierModel(inputs)
        res = model.run_simulation()
        
        t_c = res['TOUT_C']
        temps.append(t_c)
        
        diff = abs(t_c - target_T)
        print(f"{r:<10.3f} | {t_c:<10.1f} | {diff:<10.1f}")
        
        if diff < min_diff:
            min_diff = diff
            best_oc = r
            
    print("-" * 35)
    print(f"✅ Optimal O/C for T={target_T}C is approx: {best_oc:.4f}")
    
    # Also check what T we get with old calibrated Heat Loss (2.85%)
    print("\nCheck with HeatLoss=2.85% (Calibrated Case):")
    inputs['HeatLossPercent'] = 2.85
    inputs['Ratio_OC'] = current_oc # Reset to 0.86
    model = GasifierModel(inputs)
    res = model.run_simulation()
    print(f"With O/C={current_oc}, HeatLoss=2.85% -> T={res['TOUT_C']:.1f}C")

if __name__ == "__main__":
    run_sensitivity()
