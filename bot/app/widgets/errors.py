from __future__ import annotations


class TemplateRenderError(Exception):
    """Rendering or dispatch-encoding failure owned by the widget renderer."""

    def __init__(
        self, message: str, *, template_id: str | None = None, element_id: str | None = None
    ) -> None:
        self.template_id = template_id
        self.element_id = element_id
        detail = message if template_id is None else f"{template_id}: {message}"
        if element_id is not None:
            detail = f"{detail} ({element_id})"
        super().__init__(detail)
