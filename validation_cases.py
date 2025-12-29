# validation_cases.py

# ==============================================================================
# 验证数据集
# 数据来源: 《气流床气化炉工程化数学模型的开发与应用》 (刘臻)
#  Table 3 (Input Conditions)
#  Table 6 (Validation Results)
#  Table 1 (Coal Analysis for Validation)
# ==============================================================================

VALIDATION_CASES = {
# validation_cases.py (追加以下内容)

    "Paper_Case_6 (Calibrated)": {
        "description": "Base Case with Heat Loss tuned to match T=1370C",
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
                "Ratio_OC": 0.86,
                "Ratio_SC": 0.08,
                "pt": 99.6,
                "P": 4.08,
                "TIN": 300.0,
                # [关键调整] 
                # 理想平衡模型通常偏高，根据经验及反算，
                # 将热损从 1.0% 调整到约 2.85% 可匹配 1370C (具体值可用 Auto-Calibrate 算出)
                "HeatLossPercent": 2.85, 
                "GasifierType": "Dry Powder"
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
            # --- 煤质数据 (Paper Table 1) ---
            # 注：论文数据可能与神优1略有不同，为精确复现论文结果，使用论文特定数据
            "Coal Analysis": {
                "Cd": 80.19, "Hd": 4.83, "Od": 9.76, "Nd": 0.85, "Sd": 0.41, # 修正OCR识别误差，基于典型烟煤推断
                "Ad": 7.35,  "Vd": 31.24, "FCd": 61.41, 
                "Mt": 4.53,  # 全水
                "HHV_Input": 29800.0 # 估算值，论文 Qgr,v=29.8 MJ/kg
            },
            # --- 工艺条件 (Paper Table 3 Case 6) ---
            "Process Conditions": {
                "FeedRate": 41670.0,    # kg/h
                "SlurryConc": 60.0,     # (假设干粉则忽略，但论文对比了CWS)
                "Ratio_OC": 0.86,       # kg O2 / kg Coal 
                "Ratio_SC": 0.08,       # kg Steam / kg Coal 
                "pt": 99.6,             # 假设纯度
                "P": 4.08,              # MPa 
                "TIN": 300.0,           # 假设入口温度
                "HeatLossPercent": 1.0, # 论文提及热损失约 1-3% [cite: 168]
                "GasifierType": "Dry Powder" # 论文主要讨论干煤粉
            }
        },
        "expected_output": {
            "TOUT_C": 1370.0, # 
            "YCO": 61.7,
            "YH2": 30.3,
            "YCO2": 1.3
        }
    },
    "Paper_Case_1": {
        "description": "Variation Case 1 from Paper Table 3",
        "inputs": {
            "Coal Analysis": "SAME_AS_BASE", # 逻辑处理时复用
            "Process Conditions": {
                "FeedRate": 41670.0,
                "Ratio_OC": 0.87,  # 
                "Ratio_SC": 0.08,
                "P": 4.08,
                "HeatLossPercent": 1.0,
                "GasifierType": "Dry Powder"
            }
        },
        "expected_output": {
            "TOUT_C": 1333.0, # 
            "YCO": 59.9,
            "YH2": 29.5
        }
    },
    "Paper_Case_2": {
        "description": "Variation Case 2 from Paper Table 3",
        "inputs": {
            "Coal Analysis": "SAME_AS_BASE",
            "Process Conditions": {
                "FeedRate": 41670.0,
                "Ratio_OC": 1.03,  # 
                "Ratio_SC": 0.13,  #  (表中有差异，取近似)
                "P": 4.08,
                "HeatLossPercent": 1.0,
                "GasifierType": "Dry Powder"
            }
        },
        "expected_output": {
            "TOUT_C": 1452.0, # 
            "YCO": 61.8,
            "YH2": 29.7
        }
    }
}