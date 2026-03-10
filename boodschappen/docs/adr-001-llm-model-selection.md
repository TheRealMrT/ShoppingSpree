# ADR-001: LLM Model Selection for Recipe Import

**Status:** Accepted
**Date:** 2026-03-09
**Context:** Recipe import pipeline using local Ollama models

---

## Decision

Use **three separate models** for different tasks, matched to their complexity:

| Task | Model | Why |
|------|-------|-----|
| Photo OCR (image to text) | `qwen3-vl:8b` (vision) | Only vision model; reads text from images |
| Recipe extraction (text to JSON) | `qwen2.5:7b` (non-thinking) | Fast, schema-constrained, no reasoning overhead |
| Chat / meal planning | `qwen3.5:9b` (thinking) | Needs reasoning for conversational tasks |

## Key Constraints

### DO NOT use thinking models (qwen3.5, deepseek-r1, etc.) for extraction

Thinking models were tried and rejected because:

1. **Too slow** - 5+ minutes per recipe vs ~30 seconds with qwen2.5:7b
2. **`<think>` tags break parsing** - output starts with `<think>...</think>` XML blocks that must be stripped before JSON parsing. Even with stripping, the tags sometimes aren't properly closed.
3. **No accuracy gain** - the thinking doesn't help with structured extraction. The model "reasons" about ingredient names and then still gets them wrong.
4. **Overkill** - structured extraction is a pattern-matching task, not a reasoning task.

### DO use Ollama structured outputs (`format` parameter)

Instead of relying on prompt engineering alone to get valid JSON, we pass a JSON schema to Ollama's `format` parameter. This **constrains output at the token level** - the model literally cannot produce invalid JSON. This is far more reliable than any prompt instruction.

### DO use temperature=0 for extraction

Deterministic output prevents the model from "creatively" renaming ingredients (e.g., "eiermie" becoming "noedels", "sperziebonen" becoming "groene bonen").

### DO include strict copy instructions in the prompt

Even with schema enforcement, the model can still hallucinate values within the schema. The prompt explicitly says:
- KOPIEER ingredientnamen EXACT (don't translate, rename, or summarize)
- KOPIEER hoeveelheden EXACT (don't round, estimate, or change)
- Verzin GEEN ingredienten (don't invent ingredients not in source text)

## If extraction quality is still insufficient

Try these in order:

1. **Try a larger non-thinking model** - `qwen2.5:14b` or `gemma3:12b` (pull with `ollama pull`). Larger models follow instructions better without needing to "think".
2. **Try a purpose-built extraction model** - `nuextract` (phi-3-mini fine-tuned for extraction) or `Inference/Schematron` (fine-tuned for HTML-to-JSON).
3. **Never go back to thinking models for extraction** - the speed/complexity trade-off is not worth it.

## Future: when TO use thinking models

Thinking models (qwen3.5:9b or larger) are appropriate for:
- **Chat / cooking assistant** - conversational, needs reasoning
- **Meal planning** - needs to reason about nutrition, preferences, variety
- **Shopping list prediction** - needs to reason about what's already in stock
- Any task where the model needs to *reason*, not just *extract*

## Architecture

```
Photo --> [qwen3-vl:8b] --> raw text --> [qwen2.5:7b + schema] --> recipe JSON
Text  -->                               [qwen2.5:7b + schema] --> recipe JSON
URL   --> JSON-LD (no model needed) OR  [qwen2.5:7b + schema] --> recipe JSON
Chat  -->                               [qwen3.5:9b]          --> response
```
