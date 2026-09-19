"""Tests for the Gemini provider response boundary."""

from core.generator import _interaction_text


def test_interaction_text_extracts_model_output_only() -> None:
    result = {
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "Prompt"}]},
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": "First "},
                    {"modality": "image"},
                    {"type": "text", "text": "answer"},
                ],
            },
        ]
    }

    assert _interaction_text(result) == "First answer"


def test_interaction_text_handles_missing_output() -> None:
    assert _interaction_text({"steps": []}) == ""
