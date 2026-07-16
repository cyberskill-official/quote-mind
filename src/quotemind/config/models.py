"""Model routing constants - QM-SPEC-001 section 4.6. FROZEN names (parent section 12.1)."""

MODEL_PLANNER = "qwen3-max"
MODEL_CLASSIFIER = "qwen-plus"
MODEL_PARSER_TEXT = "qwen-plus"
MODEL_PARSER_VISION = "qwen-vl-ocr"
MODEL_DRAFTER = "qwen3-max"
MODEL_CRITIC = "qwen3-max"
MODEL_EMBED = "text-embedding-v4"
EMBED_DIMENSIONS = 1024  # FROZEN (parent section 12.8)

FALLBACKS: dict[str, str] = {
    "qwen3-max": "qwen-max",
    "qwen-vl-ocr": "qwen3-vl-plus",
}

# Additive convenience view for /health (TASK-009). Does not rename any frozen constant.
MODEL_CONSTANTS: dict[str, str] = {
    "planner": MODEL_PLANNER,
    "classifier": MODEL_CLASSIFIER,
    "parser_text": MODEL_PARSER_TEXT,
    "parser_vision": MODEL_PARSER_VISION,
    "drafter": MODEL_DRAFTER,
    "critic": MODEL_CRITIC,
    "embed": MODEL_EMBED,
}
