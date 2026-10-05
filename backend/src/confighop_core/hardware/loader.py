from pathlib import Path

from pydantic import ValidationError

from ..models.hardware import HardwareProfile


class HardwareProfileError(ValueError):
    pass


def load_hardware_profile(path: str | Path) -> HardwareProfile:
    try:
        return HardwareProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise HardwareProfileError("Invalid or unreadable hardware profile") from exc
