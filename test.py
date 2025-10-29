import json
from typing import Iterable, List, Optional, Union
import pandas as pd


def _coerce_cell_to_dict(cell: Union[pd.Series, dict, str, None]) -> Optional[dict]:
    """
    Best-effort conversion of a single cell into a Python dict.
    This covers common cases we see in the wild:
      - dict: already good
      - pandas Series: convert to dict via to_dict()
      - JSON string: parse it
      - None/NaN or unsupported: return None
    """
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):  # handle NaN
        return None

    if isinstance(cell, dict):
        return cell

    if isinstance(cell, pd.Series):
        return cell.to_dict()

    if isinstance(cell, str):
        cell = cell.strip()
        # Try to parse as JSON if it looks like JSON
        if (cell.startswith("{") and cell.endswith("}")) or (cell.startswith("[") and cell.endswith("]")):
            try:
                parsed = json.loads(cell)
                # We only accept dicts here; if it's a list, we'll wrap it
                if isinstance(parsed, dict):
                    return parsed
                elif isinstance(parsed, list):
                    # If the cell is actually a list of dicts, normalize as {"value": parsed}
                    return {"value": parsed}
            except json.JSONDecodeError:
                return None

    # Unsupported shape
    return None


def extract_ticket_ids_from_column(
    df: pd.DataFrame,
    col: str,
    value_key: str = "value",
    ticket_key: str = "ticket_id",
    unique: bool = True
) -> List:
    """
    Walk the given column and pull out every ticket_id inside the nested structure.

    Expected shape per cell:
        cell -> dict-like with key `value`
        cell[value_key] -> list of dicts
        each dict -> has key `ticket_id` (configurable via ticket_key)

    Returns a flat Python list of ticket_ids. If `unique=True`, preserves
    first-seen order while deduplicating.
    """
    out: List = []

    for idx, cell in df[col].items():
        cell_dict = _coerce_cell_to_dict(cell)
        if not cell_dict:
            continue

        # Grab the list under `value_key`
        nested_list = cell_dict.get(value_key, None)
        if not isinstance(nested_list, Iterable):
            continue

        for item in nested_list:
            # Common case: each item is a dict with key 'ticket_id'
            if isinstance(item, dict) and ticket_key in item:
                out.append(item[ticket_key])
            # If the item is already a scalar ticket id, we’ll accept it
            elif not isinstance(item, dict):
                out.append(item)

    if unique:
        # De-duplicate while preserving order (Python 3.7+ dict preserves insertion order)
        out = list(dict.fromkeys(out))

    return out


def combine_with_ticket_rows(
    initial_frame: pd.DataFrame,
    ticket_list: List,
    source_df: pd.DataFrame,
    ticket_col: str = "ticket_id",
    how: str = "concat",  # "concat" | "left_join"
    join_on: Optional[str] = None
) -> pd.DataFrame:
    """
    Combine `initial_frame` with rows pulled from `source_df` for the given tickets.

    Two modes:
      1) how="concat" (default): filter source_df by ticket_list, then row-wise concat with initial_frame.
      2) how="left_join": left-merge initial_frame with a filtered slice of source_df on `join_on` (or ticket_col).

    Args:
        initial_frame: Your starting DataFrame.
        ticket_list: List of ticket ids to retrieve.
        source_df: DataFrame that contains rows to be pulled using `ticket_col`.
        ticket_col: Column name in `source_df` that holds the ticket id.
        how: "concat" (union rows) or "left_join" (merge columns).
        join_on: Column name in `initial_frame` to join on (defaults to `ticket_col` if None).

    Returns:
        Combined DataFrame as per the chosen strategy.
    """
    # Step 1: guard for empty inputs
    if not isinstance(initial_frame, pd.DataFrame):
        raise TypeError("initial_frame must be a pandas DataFrame.")
    if not isinstance(source_df, pd.DataFrame):
        raise TypeError("source_df must be a pandas DataFrame.")
    if not isinstance(ticket_list, list):
        raise TypeError("ticket_list must be a list.")

    # Step 2: pull the relevant rows from source_df
    filtered = source_df[source_df[ticket_col].isin(ticket_list)].copy()

    if how == "concat":
        # Row-wise union: just stack the frames. Columns will align where possible.
        combined = pd.concat([initial_frame, filtered], ignore_index=True, sort=False)
        return combined

    elif how == "left_join":
        # Column-wise join: merge filtered columns onto initial_frame by ticket id
        key = join_on or ticket_col

        # Reduce the right side to the key plus unique payload columns (avoid duplicate key columns)
        right_cols = [c for c in filtered.columns if c != key]
        right = filtered[[key] + right_cols].drop_duplicates(subset=[key])

        merged = initial_frame.merge(right, how="left", left_on=key, right_on=key)
        return merged

    else:
        raise ValueError('Invalid "how" value. Use "concat" or "left_join".')


# --------------------------
# Example usage (you can delete this in your notebook/script)
# --------------------------
if __name__ == "__main__":
    # Pretend this column is the one with nested dict-like structures
    df_nested = pd.DataFrame({
        "payload": [
            {"value": [{"ticket_id": 101}, {"ticket_id": 102}]},
            {"value": [{"ticket_id": 103}, {"ticket_id": 102}]},  # 102 repeated
            pd.Series({"value": [{"ticket_id": 104}]}),          # Series that acts like a dict
            '{"value": [{"ticket_id": 105}, {"ticket_id": 106}]}' # JSON string form
        ],
        "other_col": ["a", "b", "c", "d"]
    })

    # Source DF that we'll pull rows from
    source_df = pd.DataFrame({
        "ticket_id": [100, 101, 102, 103, 104, 105, 200],
        "desc": ["x100", "x101", "x102", "x103", "x104", "x105", "x200"],
        "status": ["new", "open", "open", "closed", "in-progress", "new", "new"]
    })

    # Initial DF (whatever you already have)
    initial_df = pd.DataFrame({
        "ticket_id": [1, 2, 3],
        "note": ["seed-1", "seed-2", "seed-3"]
    })

    # 1) Flatten all ticket ids from df_nested["payload"]
    tickets = extract_ticket_ids_from_column(df_nested, "payload")
    print("Tickets (deduped, ordered):", tickets)
    # -> [101, 102, 103, 104, 105, 106]

    # 2a) Combine by concatenating pulled rows below the initial frame
    combined_concat = combine_with_ticket_rows(
        initial_frame=initial_df,
        ticket_list=tickets,
        source_df=source_df,
        ticket_col="ticket_id",
        how="concat"
    )
    print("\nRow-wise combined (concat):")
    print(combined_concat)

    # 2b) (Alternative) Combine by left-joining payload columns onto initial frame
    combined_join = combine_with_ticket_rows(
        initial_frame=initial_df,
        ticket_list=tickets,
        source_df=source_df,
        ticket_col="ticket_id",
        how="left_join",        # choose join mode
        join_on="ticket_id"     # join key in initial_df
    )
    print("\nColumn-wise combined (left_join):")
    print(combined_join)
