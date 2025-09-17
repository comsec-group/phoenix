import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Build and package a bitstream for the ddr5_tester "
        "using multiple SPD file(s) and multiple payload size(s)."
    )
    parser.add_argument(
        "--spd-file",
        type=str,
        nargs="+",
        help="Path(s) to the SPD file(s). Required unless --artifacts-dir is given.",
    )
    parser.add_argument(
        "--payload-size",
        type=int,
        nargs="+",
        default=[2**15],
        help="Payload size(s) for the bitstream. Multiple can be specified. Ignored if --artifacts-dir is used.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        help="Path to an existing build artifacts directory to package directly (skips build).",
    )
    return parser.parse_args()


def extract_spd_identifier(spd_file: str) -> str:
    spd_filename = os.path.basename(spd_file)
    return os.path.splitext(spd_filename)[0]


def get_git_branch():
    """Returns the current Git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown-branch"


def get_git_commit_short():
    """Returns the short Git commit hash."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown-commit"


def sanitize_for_filename(name: str) -> str:
    """Replace characters unsafe for filenames with underscores."""
    return name.replace("/", "_").replace("\\", "_").replace(" ", "_")


def package_artifacts(src_build_dir: str, spd_identifier: str, payload_size: int):
    # Create 'bitstreams' directory if not existing
    os.makedirs("bitstreams", exist_ok=True)

    # Create a temporary directory for staging
    staging_dir = tempfile.mkdtemp(prefix="packtemp_")

    # Final directory inside the ZIP -> build/ddr5_tester/
    final_dir = os.path.join(staging_dir, "build", "ddr5_tester")
    os.makedirs(final_dir, exist_ok=True)

    # Copy all files from the unique build directory
    shutil.copytree(src_build_dir, final_dir, dirs_exist_ok=True)

    # Remove the software/ folder if it exists
    software_path = os.path.join(final_dir, "software")
    if os.path.exists(software_path):
        print("[>] Removing software/ directory from package")
        shutil.rmtree(software_path, ignore_errors=True)

    # Construct the final ZIP filename
    git_branch = sanitize_for_filename(get_git_branch())
    git_commit = get_git_commit_short()
    zip_filename = f"ddr5_tester_{git_branch}_{git_commit}_{spd_identifier}_payload{payload_size}.zip"
    zip_filepath = os.path.join("bitstreams", zip_filename)

    # Create the ZIP archive
    print(f"[>] Creating zip file: {zip_filename}")
    zip_command = f'zip -r "{zip_filename}" .'
    ret = subprocess.run(
        zip_command,
        shell=True,
        executable="/bin/bash",
        cwd=staging_dir,  # Run zip from inside the staging dir
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    if ret.returncode != 0:
        print(f"[!] Packaging failed for {src_build_dir}", file=sys.stderr)
        shutil.rmtree(staging_dir, ignore_errors=True)
        return

    # Move the final ZIP to 'bitstreams' folder
    os.replace(os.path.join(staging_dir, zip_filename), zip_filepath)
    print(f"[>] Moved {zip_filename} to {zip_filepath}")

    # Cleanup
    shutil.rmtree(staging_dir, ignore_errors=True)


def main():
    args = parse_arguments()

    if args.artifacts_dir:
        # Just repackage an existing artifacts directory
        if not os.path.isdir(args.artifacts_dir):
            print(
                f"[!] Provided artifacts directory {args.artifacts_dir} does not exist.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Try to infer identifiers from folder name if possible
        folder_name = os.path.basename(os.path.normpath(args.artifacts_dir))
        parts = folder_name.split("_")
        spd_identifier = (
            sanitize_for_filename(parts[2]) if len(parts) >= 3 else "unknownspd"
        )
        payload_size = int(parts[-1]) if parts[-1].isdigit() else 0

        package_artifacts(args.artifacts_dir, spd_identifier, payload_size)
        return

    # Normal flow: build + package
    if not args.spd_file:
        print(
            "[!] You must provide --spd-file unless using --artifacts-dir.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Verify that the script is run from the correct repository path
    if not os.path.isdir("./venv"):
        print(
            "[!] This script must be run from the repository "
            "path containing the 'venv' directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    vivado_settings_default_path = "/opt/Xilinx/Vivado/2020.2/"
    os.environ["LITEX_ENV_VIVADO"] = vivado_settings_default_path
    os.environ["TARGET"] = "ddr5_tester"

    print(f"[>] LITEX_ENV_VIVADO set to {vivado_settings_default_path}")

    print("[>] Building bitstream for the following commit:")
    subprocess.run(
        "git --no-pager log -1 --pretty=format:'%h %s'",
        shell=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    for spd_file in args.spd_file:
        if not os.path.isfile(spd_file):
            print(f"Error: SPD file {spd_file} does not exist.", file=sys.stderr)
            continue

        spd_identifier = sanitize_for_filename(extract_spd_identifier(spd_file))
        real_spd_path = os.path.realpath(spd_file)

        for payload_size in args.payload_size:
            print(
                f"\n[===] Building for SPD file: {spd_file} "
                f"with payload size: {payload_size} [===]"
            )

            build_log = "build_log.txt"
            if os.path.exists(build_log):
                os.remove(build_log)

            unique_target_name = f"ddr5_tester_{spd_identifier}_{payload_size}"

            make_command = (
                f'make -j$(nproc) build TARGET_ARGS="'
                f"--l2-size 256 "
                f"--build "
                f"--iodelay-clk-freq 400e6 "
                f"--bios-lto "
                f"--rw-bios "
                f"--from-spd {real_spd_path} "
                f"--no-sdram-hw-test "
                f"--payload-size {payload_size} "
                f'--target-name {unique_target_name}" '
                f"| tee -a {build_log}"
            )

            ret = subprocess.run(
                make_command,
                shell=True,
                executable="/bin/bash",
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            if ret.returncode != 0:
                print(
                    f"[!] Build failed for SPD file {spd_file} "
                    f"with payload size {payload_size}.",
                    file=sys.stderr,
                )
                continue

            src_build_dir = os.path.join("build", unique_target_name)
            package_artifacts(src_build_dir, spd_identifier, payload_size)

    print("\n[>] Done. All built bitstreams are in the 'bitstreams' directory.")


if __name__ == "__main__":
    main()
