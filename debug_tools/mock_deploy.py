import sys
import os

# Simulate what chem_portal does:
# 1. Finds the gasifier-model root directory
# 2. Adds it to sys.path
# 3. Imports gasifier_ui

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"Added {project_root} to sys.path")

try:
    print("Attempting to import gasifier_ui...")
    import gasifier_ui
    print("✅ Successfully imported gasifier_ui")
    
    print("Checking dependencies...")
    if hasattr(gasifier_ui, 'GasifierModel'):
        print("✅ gasifier_ui.GasifierModel class found")
    else:
        print("❌ gasifier_ui.GasifierModel NOT found")
        sys.exit(1)
        
    if hasattr(gasifier_ui, 'VALIDATION_CASES'):
        print("✅ gasifier_ui.VALIDATION_CASES found")
    else:
        print("❌ gasifier_ui.VALIDATION_CASES NOT found")
        sys.exit(1)
        
    print("🎉 Mock deployment test passed!")

except ImportError as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
