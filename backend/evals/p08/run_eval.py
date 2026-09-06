"""Run with: python -m evals.p08.run_eval"""
import json

from evals.p08.cases import CASES
from evals.p08.evaluator import evaluate


def main() -> None:
    print(json.dumps(evaluate(CASES), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
