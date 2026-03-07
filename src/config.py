"""Shared configuration dataclass."""
from dataclasses import dataclass


@dataclass
class ConversionConfig:
    timeout_seconds: int = 15
    max_image_size_mb: int = 50
    headless: bool = True
