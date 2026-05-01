from dataclasses import dataclass, field
from typing import List

@dataclass
class Search:
    url: str = ""
    content: str = ""

@dataclass
class Research:
    search_history: List[Search] = field(default_factory=list)
    latest_summary: str = ""
    reflection_iteration: int = 0

@dataclass
class Paragraph:
    title: str = ""
    content: str = ""
    research: Research = field(default_factory=Research)

@dataclass
class State:
    report_title: str = ""
    paragraphs: List[Paragraph] = field(default_factory=list)