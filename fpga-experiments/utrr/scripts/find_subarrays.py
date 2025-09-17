import argparse

import pandas as pd

"""
Example usage:
    python find_subarrays.py \
        --input-file addresses_flipped_counts.csv \
        --output-file subarray_boundaries.csv \
        --row-column "attacker_row" \
        --flip-count-column "num_rows_flipped"

This extracts subarray boundaries from a CSV file based on flipped victim row counts. 
It allows specifying custom column names for row indices and flip counts.
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract subarray boundaries from a CSV file based on flipped victim row counts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-file", type=str, required=True, help="Path to the input CSV file."
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="subarray_boundaries.csv",
        help="Path to save the output CSV file.",
    )
    parser.add_argument(
        "--row-column",
        type=str,
        default="attacker_row",
        help="Column name for row indices.",
    )
    parser.add_argument(
        "--flip-count-column",
        type=str,
        default="num_rows_flipped",
        help="Column name for flipped victim row counts.",
    )
    return parser.parse_args()


def extract_subarray_boundaries(
    input_file: str, output_file: str, row_col: str, flip_count_col: str
) -> None:
    df = pd.read_csv(input_file)
    filtered_df = df[df[flip_count_col] == 1].copy()
    filtered_df["row_difference"] = filtered_df[row_col].diff().fillna(0)

    subarray_boundaries = []
    start_row = 0

    for index, row in filtered_df.iterrows():
        if row["row_difference"] == 1 or index == filtered_df.index[-1]:
            subarray_boundaries.append((start_row, row[row_col] - 1))
            start_row = row[row_col]

    subarray_df = pd.DataFrame(
        [(start, end, end - start + 1) for start, end in subarray_boundaries],
        columns=["start_row", "end_row", "size"],
    )

    subarray_df.to_csv(output_file, index=False)
    print(f"Subarray boundaries saved to '{output_file}'.")
    print(subarray_df)


def main():
    args = parse_arguments()
    extract_subarray_boundaries(
        args.input_file, args.output_file, args.row_column, args.flip_count_column
    )


if __name__ == "__main__":
    main()
