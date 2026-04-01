import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "audit_validation_cases.py"
OUT_DIR = ROOT / "generated" / "equilibrium_scans"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_scan(carbon_conversion, delta_t_wgs, delta_t_meth):
    out_file = OUT_DIR / f"scan_xc_{carbon_conversion:.3f}_wgs_{delta_t_wgs:.0f}_meth_{delta_t_meth:.0f}.json"
    cmd = [
        "python3",
        str(AUDIT_SCRIPT),
        "--solver-method",
        "Stoic",
        "--calibrate-heat-loss",
        "--carbon-conversion",
        str(carbon_conversion),
        "--delta-t-wgs",
        str(delta_t_wgs),
        "--delta-t-meth",
        str(delta_t_meth),
        "--output",
        str(out_file),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(out_file.read_text(encoding="utf-8"))
    summary = data["summary"]
    return {
        "carbon_conversion": carbon_conversion,
        "delta_t_wgs": delta_t_wgs,
        "delta_t_meth": delta_t_meth,
        "avg_comp_mae": summary["avg_comp_mae"],
        "avg_temp_abs_error_C": summary["avg_temp_abs_error_C"],
        "avg_final_warnings": summary["avg_final_warnings"],
        "output": str(out_file),
    }


def main():
    candidates = []
    for carbon_conversion in (0.975, 0.98, 0.985, 0.99, 0.995):
        for delta_t_wgs in (-50.0, 0.0, 50.0, 100.0, 150.0):
            for delta_t_meth in (-100.0, 0.0, 100.0):
                candidates.append(run_scan(carbon_conversion, delta_t_wgs, delta_t_meth))

    ranked = sorted(
        candidates,
        key=lambda x: (
            x["avg_comp_mae"] + x["avg_temp_abs_error_C"] / 80.0 + x["avg_final_warnings"] * 10.0,
            x["avg_comp_mae"],
            x["avg_temp_abs_error_C"],
        ),
    )

    summary_file = OUT_DIR / "scan_summary.json"
    summary_file.write_text(json.dumps(ranked, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in ranked[:15]:
        print(item)
    print(f"summary={summary_file}")


if __name__ == "__main__":
    main()
