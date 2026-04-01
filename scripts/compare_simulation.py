import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from gasifier.gasifier import GasifierModel


def build_inputs(case):
    inputs = case['Coal Analysis'].copy()
    inputs.update(case['Process Conditions'])
    inputs.setdefault('TIN', 300.0)
    inputs.setdefault('TR', 1400.0)
    inputs.setdefault('HHV_Method', 0)
    return inputs


def fmt(val):
    if val is None:
        return '     -'
    return f"{val:6.2f}"


def classify_temp(pred, expected):
    if expected is None:
        if pred >= 1800:
            return 'HIGH'
        if pred <= 1000:
            return 'LOW'
        return ''
    diff = pred - expected
    if abs(diff) >= 200:
        return '偏差大'
    return ''


def main(limit, output):
    path = root / 'generated' / 'validation_cases_from_kinetic.json'
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在，请先运行 scripts/generate_validation_cases.py")
    cases = json.loads(path.read_text())
    GasifierModel.print_diagnostics = lambda self: None

    records = []
    for idx, (name, case) in enumerate(sorted(cases.items())):
        if limit and idx >= limit:
            break
        model = GasifierModel(build_inputs(case))
        results = model.run_simulation()
        diag = results['diagnostics']
        expected = case['expected_output']
        pred = {
            'TOUT_C': results['TOUT_C'],
            'Y_CO': results['Y_CO_dry'],
            'Y_H2': results['Y_H2_dry'],
            'Y_CO2': results['Y_CO2_dry'],
            'Y_CH4': results['Y_CH4_dry']
        }
        rec = {
            'case': name,
            'gasifier': case['Process Conditions'].get('GasifierType', ''),
            'expected': expected,
            'predicted': pred,
            'flags': {
                'temp': classify_temp(pred['TOUT_C'], expected.get('TOUT_C')),
                'component_only': case.get('expected_meta', {}).get('only_components', False)
            },
            'diagnostics': {
                'warnings': diag['total_warnings'],
                'mass_issues': diag['mass_balance_issues'],
                'constraints': diag['constraint_violations']
            }
        }
        records.append(rec)

    header = "Case key".ljust(44) + " | " + "Pred T" + " | " + "Exp T" + " | " + "ΔT" + " | " + "Flag" + " | " + "Warn" + " | " + "Pred CO" + " | " + "Exp CO" + " | " + "Pred H2" + " | " + "Exp H2" + " | " + "Pred CO2" + " | " + "Exp CO2"
    print(header)
    print('-' * len(header))
    for rec in records:
        case = rec['case'][:44].ljust(44)
        pred = rec['predicted']
        exp = rec['expected']
        delta = fmt(pred['TOUT_C']) if exp.get('TOUT_C') is None else f"{pred['TOUT_C'] - exp['TOUT_C']:+6.2f}"
        flag = rec['flags']['temp'] or ('component-only' if rec['flags']['component_only'] else '')
        warn = f"⚠️{rec['diagnostics']['warnings']}" if rec['diagnostics']['warnings'] else ''
        cols = [fmt(pred['TOUT_C']), fmt(exp.get('TOUT_C')) if exp.get('TOUT_C') is not None else '     -', delta, flag, warn,
                fmt(pred['Y_CO']), fmt(exp.get('Y_CO')), fmt(pred['Y_H2']), fmt(exp.get('Y_H2')), fmt(pred['Y_CO2']), fmt(exp.get('Y_CO2'))]
        print(f"{case} | {cols[0]} | {cols[1]} | {cols[2]} | {cols[3]:>5} | {cols[4]:>5} | {cols[5]} | {cols[6]} | {cols[7]} | {cols[8]} | {cols[9]} | {cols[10]}")

    out_dir = root / 'generated' / 'validation'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / output).write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"\n将 {len(records)} 条记录保存到 generated/validation/{output}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='只处理前 N 个案例')
    parser.add_argument('--output', default='simulation_comparison.json', help='输出 JSON 文件名')
    args = parser.parse_args()
    main(args.limit, args.output)
