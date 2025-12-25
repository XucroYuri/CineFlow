from typing import List, Optional, Literal, Union, Any
from pydantic import BaseModel, Field, model_validator
from pathlib import Path
from datetime import datetime
import random
import string
import re

class CharacterItem(BaseModel):
    name: str
    id: Optional[str] = None
    
    def __str__(self):
        # Helper for legacy string representation logic if needed
        return f"{self.name} {self.id}" if self.id else self.name

class Asset(BaseModel):
    characters: List[CharacterItem] = Field(default_factory=list, description="List of character objects")
    scene: Optional[str] = None
    props: List[str] = Field(default_factory=list, description="List of props")

    @model_validator(mode='before')
    @classmethod
    def migrate_legacy_characters(cls, data: Any) -> Any:
        """
        Migrates legacy List[str] characters to List[CharacterItem].
        Example: ["Alice@123"] -> [{"name": "Alice", "id": "@123"}]
        """
        if isinstance(data, dict):
            chars = data.get('characters', [])
            new_chars = []
            if chars and isinstance(chars, list):
                for item in chars:
                    if isinstance(item, str):
                        # Parse string format
                        # Logic similar to _parse_name_and_id but simple here
                        # Support "Name@ID" or "Name (@ID)"
                        c_name = item
                        c_id = None
                        
                        # Try finding ID pattern @...
                        # Note: This simple migration assumes the format is somewhat standard
                        if '@' in item:
                            parts = item.split('@', 1)
                            # Cleanup name part: remove trailing parens or spaces
                            c_name = parts[0].strip().rstrip('(').strip()
                            # ID part: ensure it starts with @
                            c_id = '@' + parts[1].strip().rstrip(')')
                        
                        new_chars.append({'name': c_name, 'id': c_id})
                    else:
                        # Already dict or object
                        new_chars.append(item)
                data['characters'] = new_chars
        return data

class Segment(BaseModel):
    segment_index: int
    prompt_text: str
    image_url: Optional[str] = None
    
    # New Asset Field
    asset: Optional[Asset] = Field(default_factory=lambda: Asset())

    # Video Params
    is_pro: bool = False
    duration_seconds: int = 10
    resolution: Literal["horizontal", "vertical"] = "horizontal"
    
    # Metadata
    director_intent: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_segment_integrity(self):
        # 1. Validate Prompt
        if not self.prompt_text or not self.prompt_text.strip():
            raise ValueError("Prompt text cannot be empty.")

        # 2. Validate Duration
        allowed_normal = [10, 15]
        allowed_pro = [10, 15, 25]
        
        if self.is_pro:
            if self.duration_seconds not in allowed_pro:
                raise ValueError(f"Pro Mode duration must be one of {allowed_pro}, got {self.duration_seconds}")
        else:
            if self.duration_seconds not in allowed_normal:
                raise ValueError(f"Normal Mode duration must be one of {allowed_normal}, got {self.duration_seconds}")
        return self

class Storyboard(BaseModel):
    segments: List[Segment]
    _comment: Optional[str] = None

class GenerationTask(BaseModel):
    id: str
    source_file: Path
    segment: Segment
    version_index: int
    output_dir: Path
    
    # Unique identifiers for filename to prevent overwrite
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S"))
    random_suffix: str = Field(default_factory=lambda: ''.join(random.choices(string.ascii_lowercase + string.digits, k=4)))
    
    @property
    def output_filename_base(self) -> str:
        # Format: 1_v1_20231225120000_abcd
        return f"{self.segment.segment_index}_v{self.version_index}_{self.timestamp}_{self.random_suffix}"