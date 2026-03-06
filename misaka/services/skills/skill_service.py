"""
Skill file scanning and management service.

Discovers skill files (markdown .md) from multiple sources and provides
CRUD operations for managing them. Skill sources include global commands,
project commands, installed agent/claude skills, and plugin commands.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SkillFile:
    """Represents a single skill loaded from a markdown file.

    Attributes:
        name: The display name of the skill, using colon-separated segments
              for skills nested in subdirectories (e.g. ``subdir:skill-name``).
        description: A short human-readable description extracted from YAML
                     front-matter, or an empty string when absent.
        content: The full body text of the skill (front-matter stripped).
        source: Origin category -- one of ``"global"``, ``"project"``,
                ``"installed"``, or ``"plugin"``.
        installed_source: For installed skills only, either ``"agents"`` or
                          ``"claude"``; ``None`` for all other sources.
        file_path: Absolute path to the underlying ``.md`` file on disk.
    """

    name: str
    description: str
    content: str
    source: str  # "global" | "project" | "installed" | "plugin"
    installed_source: str | None = field(default=None)
    file_path: str = ""


def _parse_front_matter(content: str) -> tuple[str, str, str]:
    """Parse optional YAML front-matter from a markdown string.

    Front-matter is delimited by ``---`` on its own line at the very
    start of the file.  Only ``name`` and ``description`` keys are
    extracted; all other keys are silently ignored.

    Args:
        content: The raw text of the markdown file.

    Returns:
        A three-element tuple ``(name, description, body)`` where *body*
        is the remaining content after the closing ``---`` delimiter.
        If no valid front-matter block is found, *name* and *description*
        are empty strings and *body* is the original *content*.
    """
    name = ""
    description = ""
    body = content

    stripped = content.lstrip("\n")
    if not stripped.startswith("---"):
        return name, description, body

    # Find the closing --- delimiter (must appear on its own line).
    first_delim_end = stripped.index("---") + 3
    rest = stripped[first_delim_end:]

    # Skip optional newline immediately after opening ---
    if rest.startswith("\n"):
        rest = rest[1:]

    close_match = re.search(r"^---\s*$", rest, re.MULTILINE)
    if close_match is None:
        return name, description, body

    front_matter_text = rest[: close_match.start()]
    body = rest[close_match.end():]

    # Strip leading newline from body for cleanliness.
    if body.startswith("\n"):
        body = body[1:]

    # Lightweight YAML parsing -- we only need simple key: value pairs.
    for line in front_matter_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip("\"'")
        if key == "name":
            name = value
        elif key == "description":
            description = value

    return name, description, body


def _sanitize_skill_name(name: str) -> str:
    """Normalise a human-supplied skill name into a safe file-stem.

    The rules are:
    * Convert to lowercase.
    * Replace spaces with hyphens.
    * Strip every character that is not alphanumeric or a hyphen.
    * Collapse consecutive hyphens into one.
    * Strip leading/trailing hyphens.

    Args:
        name: The raw name to sanitize.

    Returns:
        A sanitized, filesystem-safe string.
    """
    sanitized = name.lower().replace(" ", "-")
    sanitized = re.sub(r"[^a-z0-9\-]", "", sanitized)
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    sanitized = sanitized.strip("-")
    return sanitized


class SkillService:
    """Discovers, reads, and manages skill files across multiple sources.

    Skill sources
    -------------
    * **Global** -- ``~/.claude/commands/*.md`` (recursive; subdirectories
      produce colon-separated names).
    * **Project** -- ``./.claude/commands/*.md`` relative to the supplied
      working directory.
    * **Installed (agents)** -- ``~/.agents/skills/*/SKILL.md``
    * **Installed (claude)** -- ``~/.claude/skills/*/SKILL.md``
    * **Plugin** -- ``~/.claude/plugins/marketplaces/*/plugins/*/commands/*.md``
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_skills(self, cwd: str | None = None) -> list[SkillFile]:
        """Scan every known source and return all discovered skill files.

        Args:
            cwd: The current working directory used to resolve the
                 *project* skill source.  When ``None``, the project
                 source is skipped.

        Returns:
            A list of :class:`SkillFile` instances.  The list may be
            empty if no skill files are found anywhere.
        """
        skills: list[SkillFile] = []

        home = Path.home()

        # 1. Global skills
        global_dir = home / ".claude" / "commands"
        skills.extend(self._scan_directory(global_dir, source="global"))

        # 2. Project skills
        if cwd is not None:
            project_dir = Path(cwd) / ".claude" / "commands"
            skills.extend(self._scan_directory(project_dir, source="project"))

        # 3. Installed skills (agents)
        agents_dir = home / ".agents" / "skills"
        skills.extend(
            self._scan_installed_skills(agents_dir, installed_source="agents")
        )

        # 4. Installed skills (claude)
        claude_skills_dir = home / ".claude" / "skills"
        skills.extend(
            self._scan_installed_skills(claude_skills_dir, installed_source="claude")
        )

        # 5. Plugin skills
        plugin_base = home / ".claude" / "plugins" / "marketplaces"
        skills.extend(self._scan_plugin_skills(plugin_base))

        deduplicated = self._deduplicate_skills(skills)
        logger.debug(
            "Discovered %d skill(s) in total (%d after dedup)",
            len(skills),
            len(deduplicated),
        )
        return deduplicated

    def read_skill(self, name: str, source: str | None = None) -> SkillFile | None:
        """Look up a single skill by name (and optionally by source).

        This performs a full scan via :meth:`list_skills` and returns the
        first matching entry.

        Args:
            name: Skill name to search for (case-insensitive).
            source: If provided, restrict matching to this source
                    (``"global"``, ``"project"``, ``"installed"``, or
                    ``"plugin"``).

        Returns:
            The matching :class:`SkillFile`, or ``None`` if not found.
        """
        skills = self.list_skills()
        name_lower = name.lower()
        for skill in skills:
            if skill.name.lower() != name_lower:
                continue
            if source is not None and skill.source != source:
                continue
            return skill
        return None

    def create_skill(
        self, name: str, content: str, scope: str = "global"
    ) -> SkillFile:
        """Create a new skill file on disk.

        Args:
            name: Human-readable skill name.  Will be sanitized for use
                  as a filename.
            content: Markdown body of the skill.
            scope: ``"global"`` writes to ``~/.claude/commands/``;
                   ``"project"`` writes to ``./.claude/commands/`` in the
                   current working directory.

        Returns:
            The newly created :class:`SkillFile`.

        Raises:
            FileExistsError: If a skill file with the derived name
                             already exists.
            ValueError: If *scope* is not ``"global"`` or ``"project"``.
        """
        safe_name = _sanitize_skill_name(name)
        if not safe_name:
            raise ValueError(f"Skill name is empty after sanitization: {name!r}")

        if scope == "global":
            base_dir = Path.home() / ".claude" / "commands"
        elif scope == "project":
            base_dir = Path.cwd() / ".claude" / "commands"
        else:
            raise ValueError(
                f"Invalid scope {scope!r}; expected 'global' or 'project'"
            )

        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / f"{safe_name}.md"

        if file_path.exists():
            raise FileExistsError(f"Skill file already exists: {file_path}")

        file_path.write_text(content, encoding="utf-8")
        logger.info("Created skill %r at %s", safe_name, file_path)

        return SkillFile(
            name=safe_name,
            description="",
            content=content,
            source=scope,
            installed_source=None,
            file_path=str(file_path),
        )

    def install_skills_from_zip(self, zip_path: str) -> list[str]:
        """Install one or more skills from a local zip archive.

        The archive is scanned for directories containing ``SKILL.md``.
        Each discovered package is copied into ``~/.claude/skills/<package>/``.

        Args:
            zip_path: Absolute path to a local ``.zip`` file.

        Returns:
            A list of installed package directory names.

        Raises:
            FileNotFoundError: If *zip_path* does not exist.
            ValueError: If the file is not a zip archive or contains no skill package.
        """
        archive = Path(zip_path)
        if not archive.is_file():
            raise FileNotFoundError(f"Zip file not found: {zip_path}")
        if archive.suffix.lower() != ".zip":
            raise ValueError("Only .zip skill packages are supported")

        skills_root = Path.home() / ".claude" / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="misaka-skill-") as temp_dir:
            temp_root = Path(temp_dir)
            self._extract_zip_to_temp(archive, temp_root)
            package_dirs = self._discover_skill_package_dirs(temp_root)
            if not package_dirs:
                raise ValueError("No valid skill package found (missing SKILL.md)")

            installed_names: list[str] = []
            for package_dir in package_dirs:
                folder_name = self._derive_package_dir_name(package_dir, archive.stem)
                target_dir = skills_root / folder_name
                self._install_package_dir(package_dir, target_dir)
                installed_names.append(folder_name)

        logger.info(
            "Installed %d skill package(s) from zip %s",
            len(installed_names),
            archive,
        )
        return installed_names

    def update_skill(
        self, name: str, content: str, source: str | None = None
    ) -> SkillFile:
        """Overwrite the content of an existing skill file.

        Args:
            name: Skill name to look up.
            content: New markdown content to write.
            source: Optional source filter passed to :meth:`read_skill`.

        Returns:
            The updated :class:`SkillFile`.

        Raises:
            FileNotFoundError: If no matching skill is found.
        """
        skill = self.read_skill(name, source=source)
        if skill is None:
            raise FileNotFoundError(f"Skill not found: {name!r}")

        path = Path(skill.file_path)
        path.write_text(content, encoding="utf-8")
        logger.info("Updated skill %r at %s", name, path)

        # Re-parse front-matter so returned object reflects new content.
        parsed_name, description, body = _parse_front_matter(content)
        return SkillFile(
            name=parsed_name or skill.name,
            description=description,
            content=body,
            source=skill.source,
            installed_source=skill.installed_source,
            file_path=skill.file_path,
        )

    def delete_skill(self, name: str, source: str | None = None) -> bool:
        """Delete a skill file from disk.

        Args:
            name: Skill name to look up.
            source: Optional source filter passed to :meth:`read_skill`.

        Returns:
            ``True`` if the file was successfully deleted, ``False`` if
            the skill could not be found.
        """
        skill = self.read_skill(name, source=source)
        if skill is None:
            logger.warning("Cannot delete skill %r: not found", name)
            return False

        path = Path(skill.file_path)
        try:
            path.unlink()
            logger.info("Deleted skill %r at %s", name, path)
            return True
        except OSError:
            logger.exception("Failed to delete skill file %s", path)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_zip_to_temp(archive: Path, target_dir: Path) -> None:
        try:
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(target_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Invalid zip archive: {archive}") from exc

    @staticmethod
    def _discover_skill_package_dirs(temp_root: Path) -> list[Path]:
        """Find package directories that contain SKILL.md."""
        skill_files = sorted(temp_root.rglob("SKILL.md"))
        if not skill_files:
            return []

        package_dirs: list[Path] = []
        seen: set[str] = set()
        for skill_file in skill_files:
            package_dir = skill_file.parent
            marker = str(package_dir.resolve(strict=False)).lower()
            if marker in seen:
                continue
            seen.add(marker)
            package_dirs.append(package_dir)
        return package_dirs

    @staticmethod
    def _derive_package_dir_name(package_dir: Path, fallback_name: str) -> str:
        raw_name = package_dir.name or fallback_name
        safe_name = _sanitize_skill_name(raw_name)
        if safe_name:
            return safe_name

        fallback_safe = _sanitize_skill_name(fallback_name)
        if fallback_safe:
            return fallback_safe
        return "skill-package"

    @staticmethod
    def _install_package_dir(package_dir: Path, target_dir: Path) -> None:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(package_dir, target_dir)

    def _scan_directory(
        self, directory: Path, source: str, prefix: str = ""
    ) -> list[SkillFile]:
        """Recursively scan *directory* for ``.md`` files.

        Subdirectory names are prepended to the skill name using a colon
        as separator (e.g. ``subdir:skill-name``).

        Args:
            directory: Root directory to scan.
            source: Source label to assign (``"global"`` or ``"project"``).
            prefix: Accumulated colon-separated prefix for recursive
                    calls.  Callers should normally leave this as ``""``.

        Returns:
            A list of :class:`SkillFile` instances discovered in this
            directory and all of its subdirectories.
        """
        skills: list[SkillFile] = []

        if not directory.is_dir():
            return skills

        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name.lower())
        except (PermissionError, OSError):
            logger.warning("Cannot read directory: %s", directory)
            return skills

        for entry in entries:
            if entry.is_dir():
                child_prefix = f"{prefix}{entry.name}:" if prefix else f"{entry.name}:"
                skills.extend(
                    self._scan_directory(entry, source=source, prefix=child_prefix)
                )
            elif entry.is_file() and entry.suffix.lower() == ".md":
                skill = self._load_skill_file(entry, source=source, prefix=prefix)
                if skill is not None:
                    skills.append(skill)

        return skills

    def _scan_installed_skills(
        self, directory: Path, installed_source: str
    ) -> list[SkillFile]:
        """Scan a directory of installed skill packages.

        Each immediate subdirectory of *directory* is expected to contain
        a ``SKILL.md`` file with optional YAML front-matter providing
        ``name`` and ``description``.

        Args:
            directory: Parent directory (e.g. ``~/.agents/skills``).
            installed_source: Either ``"agents"`` or ``"claude"``.

        Returns:
            A list of :class:`SkillFile` instances.
        """
        skills: list[SkillFile] = []

        if not directory.is_dir():
            return skills

        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name.lower())
        except (PermissionError, OSError):
            logger.warning("Cannot read directory: %s", directory)
            return skills

        for entry in entries:
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.is_file():
                continue

            try:
                raw = skill_file.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Cannot read skill file: %s", skill_file)
                continue

            parsed_name, description, body = _parse_front_matter(raw)
            name = parsed_name or entry.name

            skills.append(
                SkillFile(
                    name=name,
                    description=description,
                    content=body,
                    source="installed",
                    installed_source=installed_source,
                    file_path=str(skill_file),
                )
            )

        return skills

    def _scan_plugin_skills(self, marketplaces_dir: Path) -> list[SkillFile]:
        """Scan the plugin marketplace tree for command files.

        Expected layout::

            ~/.claude/plugins/marketplaces/<marketplace>/plugins/<plugin>/commands/*.md

        Args:
            marketplaces_dir: Path to the ``marketplaces`` directory.

        Returns:
            A list of :class:`SkillFile` instances.
        """
        skills: list[SkillFile] = []

        if not marketplaces_dir.is_dir():
            return skills

        try:
            marketplace_entries = sorted(
                marketplaces_dir.iterdir(), key=lambda e: e.name.lower()
            )
        except (PermissionError, OSError):
            logger.warning("Cannot read directory: %s", marketplaces_dir)
            return skills

        for marketplace in marketplace_entries:
            if not marketplace.is_dir():
                continue

            plugins_dir = marketplace / "plugins"
            if not plugins_dir.is_dir():
                continue

            try:
                plugin_entries = sorted(
                    plugins_dir.iterdir(), key=lambda e: e.name.lower()
                )
            except (PermissionError, OSError):
                logger.warning("Cannot read directory: %s", plugins_dir)
                continue

            for plugin in plugin_entries:
                if not plugin.is_dir():
                    continue

                commands_dir = plugin / "commands"
                if not commands_dir.is_dir():
                    continue

                try:
                    md_files = sorted(
                        commands_dir.iterdir(), key=lambda e: e.name.lower()
                    )
                except (PermissionError, OSError):
                    logger.warning("Cannot read directory: %s", commands_dir)
                    continue

                for md_file in md_files:
                    if not md_file.is_file() or md_file.suffix.lower() != ".md":
                        continue

                    skill = self._load_skill_file(
                        md_file,
                        source="plugin",
                        prefix="",
                    )
                    if skill is not None:
                        skills.append(skill)

        return skills

    @staticmethod
    def _extract_plugin_id(file_path: str) -> str | None:
        """Extract plugin directory name from a plugin skill file path.

        Path layout: .../marketplaces/<m>/plugins/<plugin>/commands/<file>.md
        Returns the <plugin> segment, or None if path does not match.
        """
        try:
            p = Path(file_path).resolve(strict=False)
            # parent = commands dir, parent.parent = plugin dir
            commands_dir = p.parent
            plugin_dir = commands_dir.parent
            if commands_dir.name.lower() != "commands":
                return None
            return plugin_dir.name.lower()
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _deduplicate_skills(skills: list[SkillFile]) -> list[SkillFile]:
        """Remove duplicate skills from multi-source scans.

        Three-pass strategy:
        1) De-duplicate by canonical file path (handles symlink/junction aliases).
        2) For installed skills only, collapse entries that have the same name and
           same content body (common when both `.agents/skills` and `.claude/skills`
           expose mirrored packages).
        3) For plugin skills, collapse entries with same (plugin_id, skill_name)
           when the same plugin exists in multiple marketplaces.
        """
        path_seen: dict[str, SkillFile] = {}
        path_order: list[str] = []

        for skill in skills:
            canonical = str(Path(skill.file_path).resolve(strict=False)).lower()
            if canonical in path_seen:
                continue
            path_seen[canonical] = skill
            path_order.append(canonical)

        installed_priority = {"agents": 0, "claude": 1, None: 2}
        installed_seen: dict[tuple[str, str], int] = {}
        plugin_seen: dict[tuple[str, str], int] = {}
        result: list[SkillFile] = []

        for canonical in path_order:
            skill = path_seen[canonical]
            if skill.source == "installed":
                key = (skill.name.strip().lower(), skill.content.strip())
                existing_idx = installed_seen.get(key)
                if existing_idx is None:
                    installed_seen[key] = len(result)
                    result.append(skill)
                else:
                    existing = result[existing_idx]
                    current_rank = installed_priority.get(skill.installed_source, 99)
                    existing_rank = installed_priority.get(existing.installed_source, 99)
                    if current_rank < existing_rank:
                        result[existing_idx] = skill
                        installed_seen[key] = existing_idx
                continue

            if skill.source == "plugin":
                plugin_id = SkillService._extract_plugin_id(skill.file_path)
                if plugin_id is not None:
                    key = (plugin_id, skill.name.strip().lower())
                    if key in plugin_seen:
                        continue
                    plugin_seen[key] = len(result)

            result.append(skill)

        return result

    # ------------------------------------------------------------------
    # File-level helper
    # ------------------------------------------------------------------

    @staticmethod
    def _load_skill_file(
        file_path: Path,
        source: str,
        prefix: str = "",
        installed_source: str | None = None,
    ) -> SkillFile | None:
        """Read and parse a single ``.md`` skill file.

        Args:
            file_path: Absolute path to the markdown file.
            source: Source label (``"global"``, ``"project"``, etc.).
            prefix: Colon-separated prefix for the skill name derived
                    from the subdirectory structure.
            installed_source: Optional installed-source qualifier.

        Returns:
            A :class:`SkillFile`, or ``None`` if the file cannot be read.
        """
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Cannot read skill file: %s", file_path)
            return None

        parsed_name, description, body = _parse_front_matter(raw)
        stem = file_path.stem  # filename without .md

        # Prefer front-matter name; fall back to filename stem.
        name = parsed_name or f"{prefix}{stem}"

        return SkillFile(
            name=name,
            description=description,
            content=body,
            source=source,
            installed_source=installed_source,
            file_path=str(file_path),
        )
