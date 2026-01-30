import sys
import os

def setup_path():
    """Add src directory to sys.path"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Assuming standard structure: root/scripts/subdir/script.py
    # We want root/src
    
    # Climb up 2 levels from debug_tools or tests (root/debug_tools/ -> root/)
    project_root = os.path.dirname(current_dir)
    src_path = os.path.join(project_root, 'src')
    
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
