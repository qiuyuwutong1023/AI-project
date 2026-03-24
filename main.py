import argparse
import logging
import os
from pathlib import Path
import subprocess
import sys


# Python 3.14 tightened argparse help-string validation, while Hydra 1.3.x
# passes a lazy help object for shell completion. Coerce to string for compat.
if sys.version_info >= (3, 14):
    _orig_check_help = argparse._ActionsContainer._check_help

    def _check_help_compat(self, action):
        if action.help is not None and not isinstance(action.help, str):
            action.help = str(action.help)
        return _orig_check_help(self, action)

    argparse._ActionsContainer._check_help = _check_help_compat

import hydra
from utils.utils import init_client, print_hyperlink


ROOT_DIR = os.getcwd()
logging.basicConfig(level=logging.INFO)

@hydra.main(version_base=None, config_path="cfg", config_name="config")
def main(cfg):
    workspace_dir = Path.cwd()
    # Set logging level
    logging.info(f"Workspace: {print_hyperlink(workspace_dir)}")
    logging.info(f"Project Root: {print_hyperlink(ROOT_DIR)}")
    logging.info(f"Using LLM: {cfg.get('model', cfg.llm_client.model)}")
    logging.info(f"Using Algorithm: {cfg.algorithm}")

    supported_problems = {"bpp_online"}
    if cfg.problem.problem_name not in supported_problems:
        raise ValueError(f"Unsupported problem '{cfg.problem.problem_name}'. Supported: {sorted(supported_problems)}")
    if cfg.algorithm != "reevo":
        raise ValueError("This repository is configured for BPP with ReEvo only. Set algorithm=reevo.")

    client = init_client(cfg)
    # optional clients for operators (ReEvo)
    long_ref_llm = hydra.utils.instantiate(cfg.llm_long_ref) if cfg.get("llm_long_ref") else None
    short_ref_llm = hydra.utils.instantiate(cfg.llm_short_ref) if cfg.get("llm_short_ref") else None
    crossover_llm = hydra.utils.instantiate(cfg.llm_crossover) if cfg.get("llm_crossover") else None
    mutation_llm = hydra.utils.instantiate(cfg.llm_mutation) if cfg.get("llm_mutation") else None
    
    from reevo import ReEvo as LHH

    # Main algorithm
    lhh = LHH(cfg, ROOT_DIR, client, long_reflector_llm=long_ref_llm, short_reflector_llm=short_ref_llm,
              crossover_llm=crossover_llm, mutation_llm=mutation_llm)
        
    best_code_overall, best_code_path_overall = lhh.evolve()
    logging.info(f"Best Code Overall: {best_code_overall}")
    best_path = best_code_path_overall.replace(".py", ".txt").replace("code", "response")
    logging.info(f"Best Code Path Overall: {print_hyperlink(best_path, best_code_path_overall)}")
    
    # Run validation and redirect stdout to a file "best_code_overall_stdout.txt"
    with open(f"{ROOT_DIR}/problems/{cfg.problem.problem_name}/gpt.py", 'w', encoding="utf-8") as file:
        file.writelines(best_code_overall + '\n')
    test_script = f"{ROOT_DIR}/problems/{cfg.problem.problem_name}/eval.py"
    test_script_stdout = "best_code_overall_val_stdout.txt"
    logging.info(f"Running validation script...: {print_hyperlink(test_script)}")
    with open(test_script_stdout, 'w', encoding="utf-8") as stdout:
        subprocess.run([sys.executable, test_script, "-1", ROOT_DIR, "val"], stdout=stdout)
    logging.info(f"Validation script finished. Results are saved in {print_hyperlink(test_script_stdout)}.")
    
    # Print the results
    with open(test_script_stdout, 'r', encoding="utf-8") as file:
        for line in file.readlines():
            logging.info(line.strip())

if __name__ == "__main__":
    main()
