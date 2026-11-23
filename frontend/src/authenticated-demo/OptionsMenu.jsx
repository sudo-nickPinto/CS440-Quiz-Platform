import { useEffect, useRef, useState } from "react";

const GAP = 8;

// Native <details> keeps this small and keyboard accessible. Selecting any
// action closes the popover so it behaves like a conventional options menu.
//
// `floating` places the open menu over the page (position: fixed) instead of
// inside its row, for menus in a box that scrolls sideways: that box would
// otherwise cut the menu off, or have to grow to make room for it. It opens
// below the ⋯ button, or above it when there's no room below, and closes on
// scroll or resize rather than drifting away from its button.
export default function OptionsMenu({ children, className = "", floating = false }) {
  const menu = useRef(null);
  const [place, setPlace] = useState(null);

  function closeAfterSelection(event) {
    if (event.target.closest("a, button")) {
      menu.current?.removeAttribute("open");
    }
  }

  function handleToggle() {
    const details = menu.current;
    if (!floating || !details) return;
    if (!details.open) {
      setPlace(null);
      return;
    }
    const button = details.querySelector("summary").getBoundingClientRect();
    const height = details.querySelector(".ui-row-options").offsetHeight;
    const viewport = document.documentElement;
    const roomBelow = viewport.clientHeight - button.bottom;
    const above = roomBelow < height + GAP * 2 && button.top > roomBelow;
    setPlace({
      position: "fixed",
      right: Math.max(GAP, viewport.clientWidth - button.right),
      left: "auto",
      ...(above
        ? { top: "auto", bottom: viewport.clientHeight - button.top + GAP }
        : { top: button.bottom + GAP, bottom: "auto" }),
    });
  }

  useEffect(() => {
    if (!place) return undefined;
    const close = (event) => {
      // Scrolling inside the menu itself is fine.
      if (event.type === "scroll" && menu.current?.contains(event.target)) return;
      menu.current?.removeAttribute("open");
      setPlace(null);
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [place]);

  return (
    <details
      ref={menu}
      className={`ui-row-menu ${className}`.trim()}
      onToggle={handleToggle}
    >
      <summary aria-label="Options" title="Options">
        <span aria-hidden="true">⋯</span>
      </summary>
      <div
        className="ui-row-options"
        // A floating menu stays hidden (but measurable) until it's placed,
        // so it never flashes in its in-row position first.
        style={place ?? (floating ? { visibility: "hidden" } : undefined)}
        onClick={closeAfterSelection}
      >
        {children}
      </div>
    </details>
  );
}
