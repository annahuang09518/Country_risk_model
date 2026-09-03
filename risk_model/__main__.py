from __future__ import annotations

from pathlib import Path

from .loader import load_model_parameters


def main() -> None:
    workbook_path = Path(__file__).resolve().parent.parent / "data" / "model_parameters.xlsx"
    params = load_model_parameters(workbook_path)
    summary = params.validation_summary()
    print("Validation summary")
    print(f"Level-3 risks: {summary['level_3_risks']}")
    print(f"Scoring indicators: {summary['scoring_indicators']}")
    print(f"Impact rules: {summary['impact_rules']}")
    print(f"Override rules: {summary['override_rules']}")
    print(f"Validation errors: {len(summary['validation_errors'])}")
    if summary["validation_errors"]:
        for error in summary["validation_errors"]:
            print(f"- {error}")
    else:
        print("- none")


if __name__ == "__main__":
    main()
