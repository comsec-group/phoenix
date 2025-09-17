import argparse
import os
import subprocess
import sys


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process a provided bitstream file for the ddr5_tester."
    )
    parser.add_argument(
        "--bitstream-file",
        required=True,
        type=str,
        help="Path to the bitstream file",
    )
    return parser.parse_args()


def validate_bitstream_file(bitstream_file: str) -> None:
    if not os.path.isfile(bitstream_file):
        print(
            f"Error: Bitstream file {bitstream_file} does not exist.", file=sys.stderr
        )
        sys.exit(1)


def setup_environment() -> None:
    vivado_settings_path: str = "/opt/Xilinx/Vivado/2020.2/"
    os.environ["LITEX_ENV_VIVADO"] = vivado_settings_path
    os.environ["TARGET"] = "ddr5_tester"
    print(f"[>] LITEX_ENV_VIVADO set to {vivado_settings_path}")


def process_bitstream(bitstream_file: str) -> str:
    log_dir: str = os.path.join(os.getcwd(), "logs-validation")
    os.makedirs(log_dir, exist_ok=True)
    print(f"[>] Processing {bitstream_file}")

    basename: str = os.path.basename(bitstream_file).replace(".zip", "")

    # Clean up previous build and extract bitstream
    if os.path.exists("build"):
        subprocess.run(["rm", "-rf", "build"], check=True)
    subprocess.run(
        ["unzip", "-qo", bitstream_file],
        check=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    return basename


def flash_bitstream() -> None:
    print("\033[1;32;40m[>] Flashing bitstream...\033[0m")
    try:
        subprocess.run(
            ["make", "flash"], check=True, stdout=sys.stdout, stderr=sys.stderr
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: Flashing failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if not os.path.isdir("./venv"):
        print(
            "[!] This script must be run from the repository "
            "path containing the 'venv' directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    args = parse_arguments()
    validate_bitstream_file(args.bitstream_file)
    setup_environment()
    process_bitstream(args.bitstream_file)
    flash_bitstream()


if __name__ == "__main__":
    main()
