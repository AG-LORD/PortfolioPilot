"""Expanding-window walk-forward splits with a purge gap.

The sorted unique dates are cut into n_blocks + 1 equal chunks (the last
test block also takes any remainder). Chunk 0 is only ever training data;
chunks 1..n_blocks are the test blocks. Block i trains on every date before
it except the last `horizon` dates, so no training label (which looks
`horizon` trading days ahead) reaches into the test block.
"""

from dataclasses import dataclass

import pandas as pd

N_TEST_BLOCKS = 5


@dataclass
class WalkForwardSplit:
    train_dates: list
    test_dates: list


def walk_forward_splits(dates, n_blocks: int = N_TEST_BLOCKS, horizon: int = 20) -> list[WalkForwardSplit]:
    unique_dates = sorted(pd.unique(pd.Series(list(dates))))
    block_length = len(unique_dates) // (n_blocks + 1)
    if n_blocks < 1 or block_length <= horizon:
        raise ValueError(
            f"{len(unique_dates)} dates are too few for {n_blocks} test block(s) with a "
            f"{horizon}-day purge gap."
        )

    splits = []
    for i in range(1, n_blocks + 1):
        test_start = i * block_length
        test_end = len(unique_dates) if i == n_blocks else (i + 1) * block_length
        splits.append(
            WalkForwardSplit(
                train_dates=unique_dates[: test_start - horizon],
                test_dates=unique_dates[test_start:test_end],
            )
        )
    return splits
