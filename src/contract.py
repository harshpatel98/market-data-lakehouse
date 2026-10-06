"""Data contract: turn a written agreement into an automated check.

See contracts/prices_daily.yaml for the contract format.
"""
import pandas as pd
import yaml


def load_contract(path: str) -> dict:
    """Load a contract YAML file into a dict."""
    with open(path) as f:
        return yaml.safe_load(f)


def validate(df: pd.DataFrame, contract: dict) -> list:
    """Return a list of violation messages (an empty list means the data passes).

    Check, in this order, and add ONE message per problem found:
      * missing column         -> "missing column: <name>"
      * wrong kind             -> "wrong kind: <name>"   (kinds: string, date, number)
      * nulls where not allowed-> "nulls in: <name>"
      * min_exclusive rule     -> "rule failed: <name> > <value>"
      * duplicate grain keys   -> "duplicate keys"
    Skip the other checks for a column that is missing.
    """
    kind_checks = {
        "string": lambda s: pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s),
        "date": pd.api.types.is_datetime64_any_dtype,
        "number": lambda s: pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s),
    }
    columns = contract.get("columns", [])
    present = [c for c in columns if c["name"] in df.columns]
    problems = [f"missing column: {c['name']}" for c in columns if c["name"] not in df.columns]

    for c in present:
        check = kind_checks.get(c.get("kind"))
        if check and not check(df[c["name"]]):
            problems.append(f"wrong kind: {c['name']}")
    for c in present:
        if not c.get("nullable", True) and df[c["name"]].isna().any():
            problems.append(f"nulls in: {c['name']}")
    for c in present:
        if "min_exclusive" in c:
            values = pd.to_numeric(df[c["name"]], errors="coerce")
            if (values <= c["min_exclusive"]).any():
                problems.append(f"rule failed: {c['name']} > {c['min_exclusive']}")

    keys = contract.get("grain_keys", [])
    if keys and all(k in df.columns for k in keys) and df.duplicated(subset=keys).any():
        problems.append("duplicate keys")
    return problems


def check_freshness(df: pd.DataFrame, contract: dict, today) -> bool:
    """True if the newest value of contract['freshness']['column'] is no more than
    max_age_days calendar days before `today`."""
    rule = contract["freshness"]
    newest = pd.to_datetime(df[rule["column"]]).max()
    if pd.isna(newest):
        return False
    age = (pd.Timestamp(today).normalize() - newest.normalize()).days
    return age <= rule["max_age_days"]
