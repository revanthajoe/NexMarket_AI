from __future__ import annotations

from typing import Iterable


def derive_improvement_instructions(*, weaknesses: Iterable[str] | None = None, suggestions: Iterable[str] | None = None) -> str:
    """Convert poster evaluation feedback into a deterministic improvement instruction."""
    findings = []
    for value in weaknesses or []:
        if value:
            findings.append(str(value))
    for value in suggestions or []:
        if value:
            findings.append(str(value))

    normalized = []
    seen = set()
    for item in findings:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(item.strip())

    actions = []
    for item in normalized:
        lowered = item.lower()
        if any(token in lowered for token in ["readability", "text", "font", "legibility"]):
            actions.append("improve text readability")
        elif any(token in lowered for token in ["cta", "call", "button"]):
            actions.append("strengthen CTA visibility")
        elif any(token in lowered for token in ["placement", "align", "layout", "subject", "position"]):
            actions.append("improve subject placement and layout balance")
        elif any(token in lowered for token in ["brand", "identity", "logo", "consistency"]):
            actions.append("improve brand consistency")
        elif any(token in lowered for token in ["contrast", "color"]):
            actions.append("improve contrast and visual hierarchy")
        elif any(token in lowered for token in ["visual", "appeal", "composition"]):
            actions.append("improve visual appeal and composition")
        else:
            actions.append(item)

    if not actions:
        return ""

    unique_actions = []
    seen_actions = set()
    for action in actions:
        key = action.lower()
        if key in seen_actions:
            continue
        seen_actions.add(key)
        unique_actions.append(action)

    return "; ".join(unique_actions[:5])
