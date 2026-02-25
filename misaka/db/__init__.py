"""
Database persistence layer for Misaka.

Provides an abstract backend interface with two implementations:
- SeekDBBackend: embedded mode for Linux/macOS
- SQLiteBackend: fallback for Windows and universal compatibility
"""
