import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class Project:
    name: str
    description: str = ""
    tech_stack: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    looking_for: list[str] = field(default_factory=list)


@dataclass
class CategoryConfig:
    description: str = ""
    weight: float = 1.0


@dataclass
class UserProfile:
    name: str = "User"
    role: str = "Developer"
    primary_interests: list[str] = field(default_factory=list)
    secondary_interests: list[str] = field(default_factory=list)
    avoid_topics: list[str] = field(default_factory=list)
    categories: dict[str, CategoryConfig] = field(default_factory=dict)
    tone: str = "Direct and concise."
    projects: list[Project] = field(default_factory=list)

    @classmethod
    def load(cls) -> "UserProfile":
        """Load profile from user_config, falling back to defaults."""
        profile_path = settings.USER_CONFIG_DIR / "profile.yaml"
        if not profile_path.exists():
            profile_path = settings.CONFIG_DIR / "default_profile.yaml"
            logger.info("No user profile found, using defaults")

        projects_path = settings.USER_CONFIG_DIR / "projects.yaml"

        profile = cls._load_profile(profile_path)
        if projects_path.exists():
            profile.projects = cls._load_projects(projects_path)

        return profile

    @classmethod
    def _load_profile(cls, path: Path) -> "UserProfile":
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        interests = data.get("interests", {})
        categories = {}
        for name, cat_data in data.get("categories", {}).items():
            if isinstance(cat_data, dict):
                categories[name] = CategoryConfig(
                    description=cat_data.get("description", ""),
                    weight=cat_data.get("weight", 1.0),
                )

        return cls(
            name=data.get("name", "User"),
            role=data.get("role", "Developer"),
            primary_interests=interests.get("primary", []),
            secondary_interests=interests.get("secondary", []),
            avoid_topics=interests.get("avoid", []),
            categories=categories,
            tone=data.get("tone", "Direct and concise."),
        )

    @classmethod
    def _load_projects(cls, path: Path) -> list[Project]:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        projects = []
        for p in data.get("projects", []):
            projects.append(Project(
                name=p.get("name", ""),
                description=p.get("description", ""),
                tech_stack=p.get("tech_stack", []),
                pain_points=p.get("pain_points", []),
                looking_for=p.get("looking_for", []),
            ))
        return projects

    def get_profile_summary(self) -> str:
        """Generate a text summary for injection into agent prompts."""
        lines = [
            f"Name: {self.name}",
            f"Role: {self.role}",
            f"Primary interests: {', '.join(self.primary_interests)}",
        ]
        if self.secondary_interests:
            lines.append(f"Secondary interests: {', '.join(self.secondary_interests)}")
        if self.avoid_topics:
            lines.append(f"Topics to avoid: {', '.join(self.avoid_topics)}")
        if self.projects:
            lines.append("\nActive projects:")
            for p in self.projects:
                lines.append(f"  - {p.name}: {p.description}")
                if p.tech_stack:
                    lines.append(f"    Tech: {', '.join(p.tech_stack)}")
                if p.pain_points:
                    lines.append(f"    Pain points: {', '.join(p.pain_points)}")
                if p.looking_for:
                    lines.append(f"    Looking for: {', '.join(p.looking_for)}")
        lines.append(f"\nPreferred tone: {self.tone}")
        return "\n".join(lines)

    def get_discovery_queries(self) -> list[str]:
        """Generate GitHub search queries from projects."""
        queries = []
        for project in self.projects:
            for term in project.looking_for:
                queries.append(term)
        return queries
