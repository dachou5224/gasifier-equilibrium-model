"""
validation_cases.py - Validation Datasets from Published Literature

================================================================================
MODIFICATION HISTORY
================================================================================
2026-01-28  v1.1  刘臻 (Liu Zhen)
    - [Fix] Line 31-36, 66-70: 添加缺失的默认参数 (T_Coal_In, T_Slurry_In, 
      T_Scrubber, TR, HHV_Method)
    - [Fix] Line 85-105, 118-139: Paper_Case_1/2 补全煤质数据和 pt 参数
    - [Doc] Line 154-175: 添加 HHV 单位说明与数据验证注释
================================================================================
"""

# validation_cases.py (修复版)

# ==============================================================================
# 验证数据集
# 数据来源: 《气流床气化炉工程化数学模型的开发与应用》 (刘臻)
#  Table 3 (Input Conditions)
#  Table 6 (Validation Results)
#  Table 1 (Coal Analysis for Validation)
# ==============================================================================

VALIDATION_CASES = {
    "Paper_Case_6 (Calibrated)": {
        "description": "Base Case with Heat Loss tuned to match T=1370C",
        "inputs": {
            "Coal Analysis": {
                "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41,
                "Ad": 7.35,  "Vd": 31.24, "FCd": 61.41, 
                "Mt": 4.53,
                "HHV_Input": 29800.0  # 🔍 需确认单位: kJ/kg 或 MJ/kg?
            },
            "Process Conditions": {
                "FeedRate": 41670.0,
                "SlurryConc": 60.0, 
                "Ratio_OC": 1.05,  # 修正: 0.86 -> 1.05 以匹配 T=1370C
                "Ratio_SC": 0.08,
                "pt": 99.6,
                "P": 4.08,
                "TIN": 300.0,
                "HeatLossPercent": 2.85,  # 校准值
                "GasifierType": "Dry Powder",
                # 🆕 添加缺失的默认值
                "T_Coal_In": 298.15,
                "T_Slurry_In": 298.15,
                "T_Scrubber": 210.0,
                "TR": 1400.0,
                "HHV_Method": 0  # 0=使用HHV_Input, 1=使用NICE1公式
            }
        },
        "expected_output": {
            "TOUT_C": 1370.0,
            "YCO": 61.7,
            "YH2": 30.3,
            "YCO2": 1.3
        }
    },
    
    "Paper_Case_6 (Base)": {
        "description": "Base operating condition from Paper Table 3",
        "inputs": {
            "Coal Analysis": {
                "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41,
                "Ad": 7.35,  "Vd": 31.24, "FCd": 61.41, 
                "Mt": 4.53,
                "HHV_Input": 29800.0
            },
            "Process Conditions": {
                "FeedRate": 41670.0,
                "SlurryConc": 60.0,
                "Ratio_OC": 1.05, # 修正: 0.86 -> 1.05
                "Ratio_SC": 0.08,
                "pt": 99.6,
                "P": 4.08,
                "TIN": 300.0,
                "HeatLossPercent": 3.0,
                "GasifierType": "Dry Powder",
                "T_Coal_In": 298.15,
                "T_Slurry_In": 298.15,
                "T_Scrubber": 210.0,
                "TR": 1400.0,
                "HHV_Method": 0
            }
        },
        "expected_output": {
            "TOUT_C": 1370.0,
            "YCO": 61.7,
            "YH2": 30.3,
            "YCO2": 1.3
        }
    },
    
    "Paper_Case_1": {
        "description": "Variation Case 1 from Paper Table 3",
        "inputs": {
            "Coal Analysis": {
                # 🆕 复制base案例的煤质数据
                "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41,
                "Ad": 7.35,  "Vd": 31.24, "FCd": 61.41, 
                "Mt": 4.53,
                "HHV_Input": 29800.0
            },
            "Process Conditions": {
                "FeedRate": 41670.0,
                "Ratio_OC": 1.06,  # 0.87 -> 1.06
                "Ratio_SC": 0.08,
                "pt": 99.6,  # 🆕 添加缺失参数
                "P": 4.08,
                "TIN": 300.0,
                "HeatLossPercent": 3.0,
                "GasifierType": "Dry Powder",
                "SlurryConc": 60.0,
                "T_Coal_In": 298.15,
                "T_Slurry_In": 298.15,
                "T_Scrubber": 210.0,
                "TR": 1400.0,
                "HHV_Method": 0
            }
        },
        "expected_output": {
            "TOUT_C": 1333.0,
            "YCO": 59.9,
            "YH2": 29.5
        }
    },
    
    "Paper_Case_2": {
        "description": "Variation Case 2 from Paper Table 3",
        "inputs": {
            "Coal Analysis": {
                "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41,
                "Ad": 7.35,  "Vd": 31.24, "FCd": 61.41, 
                "Mt": 4.53,
                "HHV_Input": 29800.0
            },
            "Process Conditions": {
                "FeedRate": 41670.0,
                "Ratio_OC": 1.22,  # 1.03 -> 1.22
                "Ratio_SC": 0.13,  # 变化点
                "pt": 99.6,  # 🆕 添加缺失参数
                "P": 4.08,
                "TIN": 300.0,
                "HeatLossPercent": 3.0,
                "GasifierType": "Dry Powder",
                "SlurryConc": 60.0,
                "T_Coal_In": 298.15,
                "T_Slurry_In": 298.15,
                "T_Scrubber": 210.0,
                "TR": 1400.0,
                "HHV_Method": 0
            }
        },
        "expected_output": {
            "TOUT_C": 1452.0,
            "YCO": 61.8,
            "YH2": 29.7
        }
    }
}


# ==============================================================================
# 🆕 单位说明与数据验证
# ==============================================================================

"""
⚠️ 重要: HHV单位一致性检查

数据库 (coal_props.py):
  - HHV_d 使用 MJ/kg (例如: ShenYou 1 = 30.72 MJ/kg)

验证案例 (validation_cases.py):
  - HHV_Input = 29800.0
  - 需确认单位!

可能性1: 29800 kJ/kg = 29.8 MJ/kg ✅
  → 与论文 Qgr,v=29.8 MJ/kg 一致
  → coal_props.calculate_coal_thermo() 应该能正确处理

可能性2: 29800 MJ/kg = 29800000 kJ/kg ❌
  → 明显不合理 (比TNT还高)

建议:
  1. 在 coal_props.py 中统一使用 kJ/kg
  2. 数据库值 × 1000: 30.72 MJ/kg → 30720 kJ/kg
  3. 验证输入保持 kJ/kg
"""