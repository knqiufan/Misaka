# Image Preview Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make all chat-related image thumbnails open the same full-screen preview overlay, and make the overlay zoom controls visibly affect the image.

**Architecture:** Reuse `misaka.ui.components.image_overlay` as the single full-screen preview entry point for both message images and pending input attachments. Fix zoom by storing the rendered image in a dedicated container whose width/height are recalculated from `_zoom_level`, instead of only updating the image control without applying any visual change.

**Tech Stack:** Python 3.10+, Flet 0.80.x, pytest

---

### Task 1: Add failing tests for overlay zoom behavior

**Files:**
- Modify: `tests/unit/test_ui_imports.py:111-117`
- Modify: `misaka/ui/components/image_overlay.py:22-168`

**Step 1: Write the failing test**

```python
def test_image_overlay_zoom_updates_rendered_size() -> None:
    from misaka.ui.components.image_overlay import ImageOverlay

    overlay = ImageOverlay(image_src="test.png")
    initial_width = overlay._image_container.width

    overlay._handle_zoom_in(None)

    assert overlay._image_container.width is not None
    assert initial_width is not None
    assert overlay._image_container.width > initial_width
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ui_imports.py -k "image_overlay_zoom_updates_rendered_size" -v`
Expected: FAIL because the overlay does not yet expose a rendered container whose dimensions change with zoom.

**Step 3: Write minimal implementation**

```python
self._image_container = ft.Container(...)

def _apply_zoom(self) -> None:
    width = int(self._base_image_width * self._zoom_level)
    height = int(self._base_image_height * self._zoom_level)
    self._image_container.width = width
    self._image_container.height = height
    self._image_container.update()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ui_imports.py -k "image_overlay_zoom_updates_rendered_size" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_ui_imports.py misaka/ui/components/image_overlay.py
git commit -m "fix: make image overlay zoom controls affect rendered size"
```

### Task 2: Add failing tests for pending-image preview click behavior

**Files:**
- Modify: `tests/unit/test_ui_imports.py`
- Modify: `misaka/ui/chat/components/image_preview_bar.py:24-177`
- Modify: `misaka/ui/chat/components/message_input.py:53-68,198-202,929-932`

**Step 1: Write the failing test**

```python
def test_message_input_pending_image_click_opens_image_overlay() -> None:
    from types import SimpleNamespace

    from misaka.ui.chat.components.message_input import MessageInput

    opened: list[object] = []
    state = SimpleNamespace(is_streaming=False)
    input_box = MessageInput(state=state, on_view_image=lambda pending: opened.append(pending))
    pending = SimpleNamespace(id="1", file_path="test.png")

    input_box._handle_view_image(pending)

    assert opened == [pending]
```

Then tighten it to the desired unified behavior by testing the preview bar callback path directly.

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ui_imports.py -k "pending_image_click_opens_image_overlay" -v`
Expected: FAIL after the test is updated to assert unified overlay opening, because the input path currently only forwards a `PendingImage` callback and does not guarantee `show_image_overlay()` is used.

**Step 3: Write minimal implementation**

Recommended implementation:

```python
from misaka.ui.components.image_overlay import show_image_overlay


def _handle_view_image(self, pending: PendingImage) -> None:
    image_src = getattr(pending, "file_path", None)
    if image_src and self.page:
        show_image_overlay(self.page, image_src)
        return
    if self._on_view_image:
        self._on_view_image(pending)
```

This keeps a safe fallback for external callers while making the default input-thumbnail click path use the same overlay as message images.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ui_imports.py -k "pending_image_click_opens_image_overlay" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_ui_imports.py misaka/ui/chat/components/message_input.py
git commit -m "feat: unify image preview for pending chat attachments"
```

### Task 3: Keep thumbnail and overlay event handling from swallowing the wrong clicks

**Files:**
- Modify: `misaka/ui/chat/components/image_preview_bar.py:42-98`
- Modify: `misaka/ui/components/image_overlay.py:34-127`
- Test: `tests/unit/test_ui_imports.py`

**Step 1: Write the failing test**

```python
def test_image_preview_thumbnail_calls_on_click() -> None:
    from types import SimpleNamespace

    from misaka.ui.chat.components.image_preview_bar import ImageThumbnail

    clicked: list[object] = []
    pending = SimpleNamespace(
        id="1",
        thumbnail=b"thumb-bytes",
        file_path="test.png",
    )
    thumb = ImageThumbnail(pending, on_click=lambda image: clicked.append(image))

    thumb._handle_click(None)

    assert clicked == [pending]
```
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ui_imports.py -k "image_preview_thumbnail_calls_on_click" -v`
Expected: FAIL if wiring is incomplete or if data assumptions in the thumbnail block prevent safe construction in tests.

**Step 3: Write minimal implementation**

- Keep the thumbnail click path simple and direct.
- Ensure the overlay backdrop closes only when the backdrop itself is clicked, not when the centered image region or control row is clicked.
- If needed, move overlay content into a centered container without `on_click=self._handle_close` on the image content container.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ui_imports.py -k "image_preview_thumbnail_calls_on_click" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_ui_imports.py misaka/ui/chat/components/image_preview_bar.py misaka/ui/components/image_overlay.py
git commit -m "fix: preserve image preview interactions in overlay and thumbnails"
```

### Task 4: Run focused regression verification

**Files:**
- Test: `tests/unit/test_ui_imports.py`

**Step 1: Run targeted tests**

Run: `pytest tests/unit/test_ui_imports.py -k "image_overlay or pending_image or thumbnail" -v`
Expected: PASS

**Step 2: Run the full related import suite**

Run: `pytest tests/unit/test_ui_imports.py -v`
Expected: PASS

**Step 3: Manual verification checklist**

- Paste a screenshot into the chat input and click its thumbnail.
- Upload an image file into the chat input and click its thumbnail.
- Click a message image.
- In the overlay, click zoom in, zoom out, and reset.
- Confirm the image visibly changes size and the controls remain clickable.

**Step 4: Commit**

```bash
git add tests/unit/test_ui_imports.py misaka/ui/chat/components/message_input.py misaka/ui/chat/components/image_preview_bar.py misaka/ui/components/image_overlay.py
git commit -m "fix: unify chat image preview overlay behavior"
```
