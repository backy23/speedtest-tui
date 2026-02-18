"""UI layer -- Rich dashboard and output formatters."""

from .dashboard import (
    ProgressDisplay,
    console,
    create_histogram,
    print_client_info,
    print_final_results,
    print_header,
    print_latency_details,
    print_server_selection,
    print_speed_result,
)
from .output import (
    create_result_json,
    format_csv_header,
    format_csv_row,
    format_text_result,
    save_json,
)

__all__ = [
    "ProgressDisplay",
    "console",
    "create_histogram",
    "create_result_json",
    "format_csv_header",
    "format_csv_row",
    "format_text_result",
    "print_client_info",
    "print_final_results",
    "print_header",
    "print_latency_details",
    "print_server_selection",
    "print_speed_result",
    "save_json",
]
