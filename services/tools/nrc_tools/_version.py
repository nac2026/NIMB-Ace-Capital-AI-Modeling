"""Tool version stamped into every ToolResponse metadata.

Bump when a tool's semantics change (not when it's just refactored) — this
goes into query_traces and becomes the ground truth for answering
'what changed between v1.0 and v1.1 of get_valuation?' during evaluation."""
TOOL_VERSION = "1.0.0"
