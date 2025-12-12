from pathlib import Path
import logging
import subprocess
import time
import shutil
from bug_fixing.src.oss_patch.project_builder import OSSPatchProjectBuilder
from bug_fixing.src.oss_patch.functions import (
    extract_sanitizer_report,
    extract_java_exception_report,
    get_builder_image_name,
    reset_repository,
    change_ownership_with_docker,
    pull_project_source,
)
from bug_fixing.src.oss_patch.globals import DEFAULT_PROJECT_SOURCE_PATH

from bug_fixing.src.oss_patch.inc_build_checker.rts_checker import analysis_log

logger = logging.getLogger(__name__)


def _detect_crash_report(stdout: str, language: str) -> bool:
    if language in ["c", "c++"]:
        return extract_sanitizer_report(stdout) is not None
    elif language == "jvm":
        if "ERROR: libFuzzer:" in stdout:
            return True
        elif "FuzzerSecurityIssueLow: Stack overflow" in stdout:
            return True
        else:
            return extract_java_exception_report(stdout) is not None
    else:
        return False


def _clean_oss_fuzz_out(oss_fuzz_path: Path, project_name: str):
    oss_fuzz_out_path = oss_fuzz_path / "build/out" / project_name
    if oss_fuzz_out_path.exists():
        change_ownership_with_docker(oss_fuzz_out_path)
        subprocess.run(
            f"rm -rf {oss_fuzz_out_path}",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class IncrementalBuildChecker:
    def __init__(self, oss_fuzz_path: Path, project_name: str, work_dir: Path):
        self.oss_fuzz_path = oss_fuzz_path
        self.project_name = project_name
        self.project_path = oss_fuzz_path / "projects" / self.project_name
        self.work_dir = work_dir

        self.build_time_without_inc_build: float | None = None
        self.build_time_with_inc_build: float | None = None

        assert self.oss_fuzz_path.exists()
        assert self.project_path.exists()

        self.project_builder = OSSPatchProjectBuilder(
            self.work_dir,
            self.project_name,
            self.oss_fuzz_path,
            project_path=self.project_path,
        )

    def test(self) -> bool:
        logger.info(f"Preparing project source code for {self.project_name}")

        proj_src_path = DEFAULT_PROJECT_SOURCE_PATH
        if proj_src_path.exists():
            change_ownership_with_docker(proj_src_path)
            shutil.rmtree(proj_src_path)
        pull_project_source(self.project_path, proj_src_path)

        logger.info(
            f'create project builder image: "{get_builder_image_name(self.oss_fuzz_path, self.project_name)}"'
        )

        cur_time = time.time()
        self.project_builder.build(proj_src_path, inc_build_enabled=False)
        image_build_time = time.time() - cur_time
        logger.info(f"Docker image build time: {image_build_time}")

        if not self._measure_time_without_inc_build(proj_src_path):
            return False

        logger.info(f"Now taking a snapshot for incremental build")
        if not self.project_builder.take_incremental_build_snapshot(proj_src_path):
            logger.error(f"Taking incremental build snapshot has failed")
            return False

        if not self._measure_time_with_inc_build(proj_src_path):
            return False

        if not self._check_against_povs(proj_src_path):
            return False

        logger.info(f"Incremental build is working correctly for {self.project_name}")

        return True

    # Testing purpose function
    def _run_pov(
        self,
        harness_name: str,
        pov_path: Path,
    ) -> tuple[bytes, bytes]:
        reproduce_command = f"python3 {self.oss_fuzz_path / 'infra/helper.py'} reproduce {self.project_name} {harness_name} {pov_path}"

        # print(runner_command)
        proc = subprocess.run(
            reproduce_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return (proc.stdout, proc.stderr)

    def _measure_time_without_inc_build(self, source_path: Path) -> bool:
        logger.info("Measuring original build time without incremental build")
        change_ownership_with_docker(self.oss_fuzz_path / "out")

        # measure consumed time
        cur_time = time.time()
        build_fail_logs = self.project_builder.build_fuzzers(source_path)
        self.build_time_without_inc_build = time.time() - cur_time

        if build_fail_logs:
            stdout, stderr = build_fail_logs
            logger.error(
                f"`build_fuzzers` failed... check out logs in `/tmp/build.log`"
            )

            with open("/tmp/build.log", "w") as f:
                f.write(stdout.decode())
                f.write(stderr.decode())

            return False

        logger.info(
            f"Build time without incremental build: {self.build_time_without_inc_build}"
        )

        change_ownership_with_docker(source_path)
        if not reset_repository(source_path):
            logger.error(f"Reset of {source_path} has failed...")
            return False

        return True

    def _measure_time_with_inc_build(self, source_path) -> bool:
        logger.info("Measuring build time with incremental build")
        change_ownership_with_docker(self.oss_fuzz_path / "out")

        # measure consumed time
        cur_time = time.time()
        build_fail_logs = self.project_builder.build_fuzzers(source_path)
        self.build_time_with_inc_build = time.time() - cur_time

        if build_fail_logs:
            stdout, stderr = build_fail_logs
            logger.error(
                f"`build_fuzzers` failed... check out logs in `/tmp/build.log`"
            )

            with open("/tmp/build.log", "w") as f:
                f.write(stdout.decode())
                f.write(stderr.decode())

            return False

        logger.info(
            f"Build time with incremental build: {self.build_time_with_inc_build}"
        )

        change_ownership_with_docker(source_path)
        if not reset_repository(source_path):
            logger.error(f"Reset of {source_path} has failed...")
            return False

        return True

    def _check_against_povs(self, source_path) -> bool:
        aixcc_dir = self.oss_fuzz_path / "projects" / self.project_name / ".aixcc"
        if not aixcc_dir.exists():
            logger.error(
                f'".aixcc" directory does not exist in {self.oss_fuzz_path / "projects" / self.project_name}'
            )
            return False

        # clean out directory of OSS-Fuzz
        _clean_oss_fuzz_out(self.oss_fuzz_path, self.project_name)

        povs_dir = aixcc_dir / "povs"
        if not povs_dir.exists():
            logger.error(f'"{povs_dir}" does not exist.')
            return False

        for pov_per_harness_dir in povs_dir.iterdir():
            harness_name = pov_per_harness_dir.name

            for pov_path in pov_per_harness_dir.iterdir():
                if not reset_repository(source_path):
                    logger.error("Repository reset has failed...")
                    return False

                pov_name = pov_path.name
                logger.info(
                    f'Checking "{pov_name}" for crash with incremental build...'
                )
                if self.project_builder.build_fuzzers(source_path):
                    return False
                stdout, _ = self._run_pov(harness_name, pov_path)

                if not _detect_crash_report(
                    stdout.decode(), self.project_builder.project_lang
                ):
                    logger.error(f'crash is not detected for "{pov_name}"')
                    print(stdout.decode())
                    return False

                patch_path = aixcc_dir / "patches" / harness_name / f"{pov_name}.diff"
                assert patch_path.exists(), patch_path

                # apply a patch
                subprocess.check_call(
                    f"git apply {patch_path}", shell=True, cwd=source_path
                )

                _clean_oss_fuzz_out(self.oss_fuzz_path, self.project_name)

                logger.info(f'Building with patch "{patch_path.name}"')
                cur_time = time.time()
                if self.project_builder.build_fuzzers(source_path):
                    return False

                build_time_with_patch = time.time() - cur_time
                logger.info(
                    f'Build time with incremental build and patch ("{patch_path.name}"): {build_time_with_patch}'
                )

                stdout, _ = self._run_pov(harness_name, pov_path)

                if _detect_crash_report(str(stdout), self.project_builder.project_lang):
                    logger.error(
                        f'crash is detected for "{pov_name}" with a patch "{patch_path}"'
                    )
                    return False

                logger.info(f'Incremental build for "{pov_name}" has been validated')

        return True

    def test_with_rts(self, rts_tool: str = "jcgeks") -> bool:
        """Test RTS (Regression Test Selection) functionality.

        Measures test execution time with and without RTS optimizations.
        Similar to incremental build test - measures time before and after
        docker commit (snapshot).

        Only supported for JVM projects.

        Args:
            rts_tool: RTS tool to use (ekstazi or jcgeks)

        Returns:
            True if RTS test passes, False otherwise
        """
        if self.project_builder.project_lang != "jvm":
            logger.error("RTS is only supported for JVM projects")
            return False

        logger.info(f"Starting RTS benchmark for {self.project_name} with tool '{rts_tool}'")

        # Prepare project source
        proj_src_path = DEFAULT_PROJECT_SOURCE_PATH
        if proj_src_path.exists():
            change_ownership_with_docker(proj_src_path)
            shutil.rmtree(proj_src_path)
        pull_project_source(self.project_path, proj_src_path)

        # Build docker image
        logger.info(
            f'Creating project builder image: "{get_builder_image_name(self.oss_fuzz_path, self.project_name)}"'
        )
        cur_time = time.time()
        self.project_builder.build(proj_src_path, inc_build_enabled=False)
        image_build_time = time.time() - cur_time
        logger.info(f"Docker image build time: {image_build_time:.2f}s")

        # Step 1: Measure test time WITHOUT RTS (before snapshot)
        if not self._measure_test_time_without_rts(proj_src_path, rts_tool):
            return False

        # Step 2: Take snapshot with RTS initialization (docker commit)
        logger.info(f"Taking snapshot with RTS initialization (tool: {rts_tool})...")
        if not self.project_builder.take_incremental_build_snapshot(
            proj_src_path, rts_enabled=True, rts_tool=rts_tool
        ):
            logger.error("Taking RTS snapshot has failed")
            return False

        # Step 3: Measure test time WITH RTS (after snapshot)
        if not self._measure_test_time_with_rts(proj_src_path, rts_tool):
            return False

        # Summary
        self._print_rts_summary(rts_tool)

        return True

    def _measure_test_time_without_rts(self, source_path: Path, rts_tool: str) -> bool:
        """Measure test time without RTS (before snapshot)."""
        logger.info("Measuring test time without RTS (before snapshot)...")

        log_file = self.work_dir / "test_no_rts.log"
        cur_time = time.time()
        result = self.project_builder.run_tests(
            source_path, rts_enabled=False, log_file=log_file
        )
        self.test_time_without_rts = time.time() - cur_time

        if result:
            stdout, stderr = result
            logger.error("Test execution without RTS failed")
            logger.error(f"stdout: {stdout.decode()}")
            logger.error(f"stderr: {stderr.decode()}")
            return False

        logger.info(f"Test time without RTS: {self.test_time_without_rts:.2f}s")

        # Analyze log
        if log_file.exists():
            stats = analysis_log(log_file)
            self.stats_no_rts = stats
            logger.info(f"Tests run (no RTS): {stats[0]}, Total time: {stats[1]:.2f}s")

        # Reset repository
        change_ownership_with_docker(source_path)
        if not reset_repository(source_path):
            logger.error("Repository reset failed")
            return False

        return True

    def _measure_test_time_with_rts(self, source_path: Path, rts_tool: str) -> bool:
        """Measure test time with RTS (after snapshot).

        Applies a patch from .aixcc/patches/ before running tests to simulate code changes.
        Uses the first patch file found (sorted by name).
        """
        logger.info(f"Measuring test time with RTS (after snapshot, tool: {rts_tool})...")

        # Find and apply patch from .aixcc/patches/
        aixcc_dir = self.project_path / ".aixcc"
        patches_dir = aixcc_dir / "patches"
        patch_path = None

        if patches_dir.exists():
            # Find all .diff files recursively and sort by name
            diff_files = sorted(patches_dir.rglob("*.diff"))
            if diff_files:
                patch_path = diff_files[0]

        if patch_path:
            logger.info(f"Applying patch: {patch_path}")
            try:
                subprocess.check_call(
                    f"git apply {patch_path}",
                    shell=True,
                    cwd=source_path,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                logger.error(f"Failed to apply patch: {patch_path}")
                return False
        else:
            logger.warning(f"No patch found in {patches_dir}, running without patch")

        log_file = self.work_dir / "test_with_rts.log"
        cur_time = time.time()
        result = self.project_builder.run_tests(
            source_path, rts_enabled=True, rts_tool=rts_tool, log_file=log_file
        )
        self.test_time_with_rts = time.time() - cur_time

        if result:
            stdout, stderr = result
            logger.error("Test execution with RTS failed")
            logger.error(f"stdout: {stdout.decode()}")
            logger.error(f"stderr: {stderr.decode()}")
            return False

        logger.info(f"Test time with RTS: {self.test_time_with_rts:.2f}s")

        # Analyze log
        if log_file.exists():
            stats = analysis_log(log_file)
            self.stats_with_rts = stats
            logger.info(
                f"Tests run (with RTS): {stats[0]}, Total time: {stats[1]:.2f}s, JCG time: {stats[2]:.2f}s"
            )

        return True

    def _print_rts_summary(self, rts_tool: str):
        """Print RTS benchmark summary."""
        logger.info("=" * 60)
        logger.info(f"RTS Benchmark Results (tool: {rts_tool}):")
        logger.info("-" * 60)

        # Time comparison
        logger.info("[Time Comparison]")
        logger.info(f"  Without RTS (before snapshot): {self.test_time_without_rts:.2f}s")
        logger.info(f"  With RTS (after snapshot):     {self.test_time_with_rts:.2f}s")
        if self.test_time_without_rts > 0 and self.test_time_with_rts > 0:
            time_saved = self.test_time_without_rts - self.test_time_with_rts
            speedup = self.test_time_without_rts / self.test_time_with_rts
            reduction_pct = (time_saved / self.test_time_without_rts) * 100
            logger.info(f"  Time saved: {time_saved:.2f}s ({reduction_pct:.1f}% reduction)")
            logger.info(f"  Speedup: {speedup:.2f}x")

        # Test count comparison (from log analysis)
        if hasattr(self, 'stats_no_rts') and hasattr(self, 'stats_with_rts'):
            logger.info("-" * 60)
            logger.info("[Test Count Comparison]")

            tests_no_rts = self.stats_no_rts[0]
            tests_with_rts = self.stats_with_rts[0]
            tests_skipped = tests_no_rts - tests_with_rts

            logger.info(f"  Tests run without RTS: {tests_no_rts}")
            logger.info(f"  Tests run with RTS:    {tests_with_rts}")
            logger.info(f"  Tests skipped by RTS:  {tests_skipped}")
            if tests_no_rts > 0:
                selection_pct = (tests_with_rts / tests_no_rts) * 100
                logger.info(f"  Test selection rate:   {selection_pct:.1f}%")

            # Test class comparison
            classes_no_rts = len(self.stats_no_rts[3])
            classes_with_rts = len(self.stats_with_rts[3])
            logger.info(f"  Test classes without RTS: {classes_no_rts}")
            logger.info(f"  Test classes with RTS:    {classes_with_rts}")

            # JCG overhead
            jcg_time = self.stats_with_rts[2]
            if jcg_time > 0:
                logger.info("-" * 60)
                logger.info("[RTS Overhead]")
                logger.info(f"  JCG analysis time: {jcg_time:.2f}s")

            # Failure/Error/Skip comparison
            failures_no_rts, errors_no_rts, skips_no_rts = self.stats_no_rts[5]
            failures_with_rts, errors_with_rts, skips_with_rts = self.stats_with_rts[5]
            logger.info("-" * 60)
            logger.info("[Test Results]")
            logger.info(f"  Without RTS - Total Runs: {tests_no_rts}, Failures: {failures_no_rts}, Errors: {errors_no_rts}, Skipped: {skips_no_rts}")
            logger.info(f"  With RTS    - Total Runs: {tests_with_rts}, Failures: {failures_with_rts}, Errors: {errors_with_rts}, Skipped: {skips_with_rts}")

        logger.info("=" * 60)
