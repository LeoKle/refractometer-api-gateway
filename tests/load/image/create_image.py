import argparse
import json
from pathlib import Path

import numpy as np

ALLOWED_DTYPES = ["float32", "float64", "uint8", "uint16", "int16", "int32"]


def build_matrix(rows: int, cols: int, dtype: str) -> np.ndarray:
    values = np.arange(rows * cols, dtype=np.int64)
    if np.issubdtype(np.dtype(dtype), np.integer):
        # keep values inside the dtype's range instead of silently overflowing
        values %= np.iinfo(dtype).max + 1
    return values.astype(dtype).reshape(rows, cols)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an image payload for k6 load tests.")
    parser.add_argument("-o", "--output", default=None, help="Default: payload.bin or payload.json")
    parser.add_argument("--rows", type=int, default=2556)
    parser.add_argument("--cols", type=int, default=2440)
    parser.add_argument("--dtype", choices=ALLOWED_DTYPES, default="float32")
    parser.add_argument(
        "--format",
        choices=["raw", "json"],
        default="raw",
        help="raw = bytes for POST /api/image/raw, json = legacy POST /api/image",
    )
    args = parser.parse_args()

    if args.rows <= 0 or args.cols <= 0:
        parser.error("--rows and --cols must be positive integers")

    matrix = build_matrix(args.rows, args.cols, args.dtype)

    if args.format == "raw":
        output_path = Path(args.output or "payload.bin")
        output_path.write_bytes(matrix.tobytes())  # C-order, same layout the server stores
    else:
        output_path = Path(args.output or "payload.json")
        # the legacy endpoint takes floats; use float64 to match what the DB stored before
        payload = {"values": matrix.astype(np.float64).tolist(), "shape": [args.rows, args.cols]}
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

    print(f"Wrote {args.rows} x {args.cols} {args.format} payload to {output_path}")
    print(f"Total values: {matrix.size:,}")
    print(f"File size: {output_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()