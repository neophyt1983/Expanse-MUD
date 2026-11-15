"""Read-only diagnosis of Expanse's Render guest-account environment setting.

Upload this file beside render_server.py. Temporarily use the Render Start Command:
    python diagnose_guest_config.py && python render_server.py

The output contains only fixed labels, booleans, counts and JSON error positions.
It never prints credentials, account names, environment text or text excerpts.
No setting, account, world, save, file or database is changed.
After diagnosis, restore the normal Start Command: python render_server.py
"""

import json
import os
import re


VARIABLE = "EXPANSE_GUESTS_JSON"
MARKER = "EXPANSE_GUEST_DIAGNOSTIC_20261115_1"


def inspect_guest_config(environment):
    # Match render_server.Accounts exactly. A missing value defaults to [],
    # whereas an explicitly configured blank value remains a parsing error.
    raw = environment.get(VARIABLE, "[]")
    result = {
        "diagnostic": MARKER,
        "variable": VARIABLE,
        "variable_present": VARIABLE in environment,
        "value_is_blank": not raw.strip(),
    }
    try:
        guests = json.loads(raw)
    except json.JSONDecodeError as error:
        # Never print error.doc, repr(error), raw, slices or character codes.
        result.update({
            "json_syntax_valid": False,
            "error_line": error.lineno,
            "error_column": error.colno,
            "error_position": error.pos,
            "starts_with_array_then_object": bool(re.match(r'^\s*\[\s*\{', raw)),
            "first_property_has_straight_double_quote": bool(re.match(r'^\s*\[\s*\{\s*"', raw)),
            "first_property_has_single_quote": bool(re.match(r"^\s*\[\s*\{\s*'", raw)),
            "first_property_has_curly_quote": bool(re.match(r'^\s*\[\s*\{\s*[\u201c\u201d\u2018\u2019]', raw)),
            "first_name_property_is_unquoted": bool(re.match(r'^\s*\[\s*\{\s*name\s*:', raw)),
            "starts_with_markdown_fence": raw.lstrip().startswith("```"),
            "starts_with_variable_assignment": bool(re.match(r'^\s*(?:export\s+)?EXPANSE_GUESTS_JSON\s*=', raw)),
            "starts_with_bom": raw.startswith("\ufeff"),
            "result": "STOP_INVALID_JSON",
        })
        return result, 1
    except (ValueError, RecursionError):
        result.update({"json_syntax_valid": False, "result": "STOP_JSON_PARSER_LIMIT"})
        return result, 1

    result["json_syntax_valid"] = True
    result["root_is_array"] = isinstance(guests, list)
    if not result["root_is_array"]:
        result["result"] = "STOP_EXPECTED_ARRAY"
        return result, 1

    result["guest_count"] = len(guests)
    result["all_entries_are_objects"] = all(isinstance(row, dict) for row in guests)
    if not result["all_entries_are_objects"]:
        result["result"] = "STOP_EXPECTED_ACCOUNT_OBJECTS"
        return result, 1

    result["all_names_are_nonempty_text"] = all(
        isinstance(row.get("name"), str) and bool(row["name"].strip())
        for row in guests
    )
    result["all_passwords_are_text"] = all(
        isinstance(row.get("password"), str) for row in guests
    )
    result["all_password_lengths_are_valid"] = all(
        isinstance(row.get("password"), str) and 15 <= len(row["password"]) <= 128
        for row in guests
    )
    if not result["all_names_are_nonempty_text"]:
        result["result"] = "STOP_NAME_FIELD"
        return result, 1
    if not result["all_passwords_are_text"]:
        result["result"] = "STOP_PASSWORD_TYPE"
        return result, 1
    if not result["all_password_lengths_are_valid"]:
        result["result"] = "STOP_PASSWORD_LENGTH"
        return result, 1

    # The server still checks normalized names, duplicates, expiry and owner
    # credentials. This diagnostic does not authorize or provision an account.
    result["result"] = "PASS_CONTINUE_TO_SERVER_VALIDATION"
    return result, 0


def main():
    result, status = inspect_guest_config(os.environ)
    print(json.dumps(result, sort_keys=True), flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
