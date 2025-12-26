# Entrained Flow Gasifier Equilibrium Model (EFG-EM)

## 1. Project Overview
This project implements a comprehensive **thermodynamic equilibrium model** for entrained flow coal gasifiers (e.g., GE/Texaco, Shell). It predicts reactor performance, syngas composition, and quench outlet conditions based on coal properties and operating parameters.

The core algorithm uses **Gibbs Free Energy Minimization** (RGibbs) with mechanism constraints to handle high-pressure methanation issues.

### Key Features
* **Dual Interface**:
    * **Web UI (Streamlit)**: Modern, interactive dashboard with charts and auto-calibration.
    * **Desktop UI (Tkinter)**: Legacy lightweight interface.
* **Core Physics**:
    * **RGibbs Solver**: `scipy.optimize.minimize` with SLSQP method.
    * **Thermodynamics**: NIST Shomate equations (High/Low Temp switching).
    * **Quench Model**: Saturation calculation using Antoine equations.
* **Coal Utilities**:
    * **NICE1 & SIMTECH**: Algorithms for HHV and Enthalpy of Formation estimation.
    * **Database**: Built-in library of typical coals (ShenYou, etc.).
* **Smart Calibration**: Automatically reverse-calculates Heat Loss or O/C Ratio to match a target reactor temperature.

---

## 2. File Structure

* `app.py`: **[New]** The Streamlit web application (Recommended).
* `gasifier.py`: The physics engine (Gibbs solver, Energy balance, Quench logic).
* `coal_props.py`: Coal property calculations and database.
* `thermo_data.py`: Thermodynamic database (NIST coefficients).
* `validation_cases.py`: Validation datasets from literature.
* `main_gui.py`: The Tkinter desktop GUI.

---

## 3. Installation & Usage

### Prerequisites
* Python 3.8+
* Required libraries:
    ```bash
    pip install numpy scipy pandas streamlit plotly
    ```
    *(Note: `tkinter` is usually included with Python)*

### Method 1: Running the Web App (Recommended)
This launches a browser-based dashboard with interactive charts and tables.
```bash
streamlit run app.py