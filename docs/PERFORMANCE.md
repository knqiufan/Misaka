# UI Performance Guidelines

## Core Principle

**Prioritize GUI runtime performance**. All UI-related decisions should consider performance as the primary factor.

## Flet 0.80.x Guidelines

### Component Writing

- All Flet components must use the 0.80.x API, importing from `flet` module (not `flutter`)
- Prefer built-in Flet components over custom rendering
- When custom rendering is required, use `ft.Canvas` + `ft.CanvasControl`

### Event Handling

- Use standard callbacks: `on_click`, `on_change`, `on_hover`, etc.
- Avoid manually binding `page.on_event` unless absolutely necessary

### State Management

- Prefer Flet's `Control` subclass + `update()` method
- Avoid manually rebuilding the entire control tree
- Use `ft.ListView` / `ft.GridView` with `on_tap` callbacks for virtual scrolling

## Performance Optimization

### Async Operations

- **Never block the main thread**: File I/O, network requests, complex calculations must be async
- Use `page.run_task()` for async operations triggered from sync UI handlers
- Keep UI responsive at all times

### Control Count

- **Target**: Under 100 controls per page
- **Exceeded?** Use pagination, virtualization, or lazy loading
- Use `ft.ListView` with `item_extent` for large lists

### Update Batching

- Avoid frequent `update()` calls
- Batch state changes: merge multiple updates into a single call
- Consider using a debounce pattern for rapid state changes

### Image/Resource Loading

- Use `ft.Image.src_base_width`/`src_base_height` to specify dimensions
- Enable caching with `cache` parameter when appropriate
- Lazy load images that are not visible

### Layout Optimization

- Avoid excessive nesting: keep control tree depth under 10 levels
- Use `ft.Container` sparingly; prefer simpler layout controls
- Use `expand` and `flex` properties for flexible layouts

### Debug Mode

- Use `page.show_debug_banner = False` to hide debug banner in production
- Consider `page.platform_view_overlay` for optimizing layered rendering

## Performance Checklist

Before any UI code is considered complete:

- [ ] No blocking operations on main thread
- [ ] Control count under 100 per page
- [ ] Large lists use virtual scrolling
- [ ] State updates are batched
- [ ] Control tree depth under 10
- [ ] Debug banner disabled in production

## Profiling

Use Flet's built-in debugging tools:
- `page.debug_portal` for widget inspection
- Check the Flutter DevTools integration for performance analysis

## Common Pitfalls

1. **Creating controls in loops**: Build only what's visible, use ListView
2. **Updating parent on every child change**: Batch updates at container level
3. **Heavy computations in event handlers**: Move to background tasks
4. **Not using `item_extent`**: Causes layout recalculation on every scroll
