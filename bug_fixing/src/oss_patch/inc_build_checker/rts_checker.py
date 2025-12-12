"""
RTS (Regression Test Selection) Checker Module.

Ported from RTSTool.py with adaptations for oss-crs integration.
"""

from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)


def _convert_time_to_seconds(time_str: str) -> float:
    """Convert Maven time format to seconds.

    Ported from RTSTool.py's cover_time_to_second method.
    """
    time_str = time_str.strip()
    time_second = 0

    if time_str.endswith("s") or time_str.endswith("S"):
        time_second = float(time_str.rstrip("sS"))
    elif time_str.endswith("min"):
        time_pure = time_str.replace("min", "")
        if ":" in time_pure:
            time_min, time_sec = time_pure.split(":")
            time_second = 60 * float(time_min) + float(time_sec)
        else:
            time_second = float(time_pure) * 60
    elif time_str.endswith("h"):
        time_pure = time_str.replace("h", "")
        if ":" in time_pure:
            time_h, time_min = time_pure.split(":")
            time_second = 3600 * float(time_h) + 60 * float(time_min)
        else:
            time_second = float(time_pure) * 3600
    else:
        try:
            time_second = float(time_str)
        except ValueError:
            time_second = 0
    return time_second


def analysis_log(log_file: Path):
    """Analyze a Maven test log file and extract statistics.

    Ported from RTSTool.py's analysis_log method.

    Returns:
        [test_run, total_time, jcg_time, run_classes_list, output_class_set, [failure, error, skip]]
    """
    # [test_run, Total time, JCG Time, run classes list, output testClass set, [failure, error, skip]]
    analysis_res = [0, 0, 0, [], set(), [0, 0, 0]]

    if not os.path.exists(log_file):
        logger.warning(f"Log file does not exist: {log_file}")
        return analysis_res

    logger.info(f"[INFO] analysing log file: {log_file}")

    with open(log_file, "r", encoding="utf-8", errors="replace") as log_f:
        lines = log_f.readlines()
        for line_count in range(len(lines)):
            line = lines[line_count]

            if "Results :" in line or "Results:" in line:
                curr_idx = line_count + 2
                found_flag = True
                while True:
                    if curr_idx >= len(lines):
                        found_flag = False
                        break
                    curr_line = lines[curr_idx]
                    if "Tests run: " in curr_line:
                        result_list = (
                            curr_line.replace("\n", "").replace(" ", "").split(",")
                        )
                        break
                    elif "[INFO] ---" in curr_line:
                        found_flag = False
                        break
                    else:
                        curr_idx = curr_idx + 1

                if found_flag == False:
                    continue

                # compute tests run
                test_run_num = result_list[0].split(":")[1]
                analysis_res[0] = analysis_res[0] + int(test_run_num)

                # compute failures
                failures_num = result_list[1].split(":")[1]
                analysis_res[5][0] = analysis_res[5][0] + int(failures_num)

                # compute errors
                errors_num = result_list[2].split(":")[1]
                analysis_res[5][1] = analysis_res[5][1] + int(errors_num)

                # compute skipped
                skipped_str = result_list[3].split(":")[1]
                skipped_num = ""
                for ch in skipped_str:
                    if ch.isdigit():
                        skipped_num += ch
                analysis_res[5][2] = analysis_res[5][2] + int(skipped_num)

            elif "Total time:" in line:
                total_time = _convert_time_to_seconds(
                    line.replace("\n", "").split("Total time:")[1].replace(" ", "")
                )
                analysis_res[1] = total_time

            elif "JCG Time:" in line:
                jcg_time = _convert_time_to_seconds(
                    line.replace("\n", "").split("JCG Time:")[1].replace(" ", "")
                )
                analysis_res[2] += jcg_time

            elif "nonAffectedClasses size" in line and " final time : " in line:
                jcg_analysis_time = _convert_time_to_seconds(
                    line.replace("\n", "").split(" final time : ")[1].replace(" ", "")
                )
                analysis_res[2] += jcg_analysis_time

            elif "Running " in line:
                run_class = line.split("Running ")[1].replace("\n", "")
                analysis_res[3].append(run_class)

            elif "[RTS CHECK TAG]" in line:
                output_class = line.replace("[RTS CHECK TAG] ", "").split(" -> ")[0]
                if "$" in output_class:
                    output_class = output_class.split("$")[0]
                analysis_res[4].add(output_class)

    return analysis_res
