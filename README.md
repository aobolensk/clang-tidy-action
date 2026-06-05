# Clang-Tidy Analysis

GitHub Action for running `clang-tidy` on changed C/C++ files in a pull request.

It compares the PR branch against the base ref, skips configured directories, and writes the number of detected diagnostics to `total_comments`. If a `.clang-tidy` file changed, it analyzes all source files.

## Usage

```yaml
name: clang-tidy

on:
  pull_request:

jobs:
  clang-tidy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Configure
        run: cmake -S . -B build

      - name: Run clang-tidy
        uses: aobolensk/clang-tidy-action@v1
        with:
          build_dir: build
          exclude: 3rdparty
          clang_tidy_version: 21
```

## Inputs

- `build_dir`: CMake build directory. Default: `build`.
- `exclude`: space-separated directories to skip. Default: `3rdparty`.
- `clang_tidy_version`: uses `clang-tidy-<version>`. Default: `21`.

## Output

- `total_comments`: total clang-tidy diagnostics found.

## Requirements

The runner must have `clang-tidy-<version>` on `PATH` and a populated CMake build directory.
