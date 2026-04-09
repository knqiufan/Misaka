# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] - 2026-04-09

### Added

- Add chat group mode: switch between "group by project" and "group by date" views via sidebar toggle
- Add session archive/unarchive functionality via right-click menu
- Add token usage display in chat interface footer (context window usage indicator)
- Add MCP server configuration loading from project-level `.mcp.json`
- Add runtime log viewer in settings with in-memory ring buffer (200 entries, auto-sanitized)
- Add copy message functionality for user messages (context menu)
- Add copy reply functionality for assistant message items
- Add context menu for skill management in ExtensionsPage

### Changed

- Improve type hinting in `_split_code_blocks` and message item component
- Simplify label assignment logic in chat list
- Enhance skill management UI interactions

### Fixed

- Fix mypy 1.20.0 `str-unpack` error in message item component

## [0.1.5] - 2026-03-29

### Fixed

- Resolve Ruff SIM108/SIM102 in `message_input` (CI)

## [0.1.4] - 2026-03-29

### Changed

- Enhance file reference management in message input

## [0.1.1] - 2025-03-18

### Added

- Add "Open Releases" button in Misaka update section — direct link to GitHub latest release page for manual download
- Add delete functionality for CLI sessions

### Changed

- Replace in-app update check with direct GitHub Release link in settings (Misaka update card)
- Update session mode and improve content handling

### Fixed

- Refresh streaming message in chat component
- Refresh session list after importing CLI sessions (#7)
- Use GitHub icon and align with author in about section (#9)
- Resolve issues with session management and UI updates

### Documentation

- Update README files with new features and images
- Add CI/CD guide and exclude docs from git tracking

[Unreleased]: https://github.com/knqiufan/Misaka/compare/v0.1.6...HEAD
[0.1.6]: https://github.com/knqiufan/Misaka/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/knqiufan/Misaka/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/knqiufan/Misaka/compare/v0.1.3...v0.1.4
[0.1.1]: https://github.com/knqiufan/Misaka/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/knqiufan/Misaka/releases/tag/v0.1.0
