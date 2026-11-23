import { useEffect, useRef, useState } from "react";

const GAP = 8;

// The nearest parent that scrolls sideways, which also cuts off anything
// that sticks out below it.
function sidewaysScroller(element) {
  for (let node = element.parentElement; node; node = node.parentElement) {
    const { overflowX } = getComputedStyle(node);
    if (overflowX === "auto" || overflowX === "scroll") return node;
  }
  return null;
}

// Native <details> keeps this small and keyboard accessible. Selecting any
// action closes the popover so it behaves like a conventional options menu.
//
// `inScroller` is for menus inside a box that scrolls sideways (a wide
// table), which would cut off a menu opened on its last rows. While the menu
// is open the box lets it hang out below, as usual, so it always opens
// downward. Only if the box is actually scrolled sideways right then would
// that undo the scroll, so the menu floats over the page instead (and closes
// on scroll or resize rather than drifting away from its button).
export default function OptionsMenu({ children, className = "", inScroller = false }) {
  const menu = useRef(null);
  const opened = useRef(null);
  // null until the open menu is placed: "inline" or a floating position.
  const [floatAt, setFloatAt] = useState(null);

  function closeAfterSelection(event) {
    if (event.target.closest("a, button")) {
      menu.current?.removeAttribute("open");
    }
  }

  function release() {
    if (opened.current) delete opened.current.dataset.menuOpen;
    opened.current = null;
    setFloatAt(null);
  }

  function handleToggle() {
    const details = menu.current;
    if (!inScroller || !details) return;
    if (!details.open) {
      release();
      return;
    }
    const scroller = sidewaysScroller(details);
    if (!scroller || scroller.scrollWidth <= scroller.clientWidth + 1) {
      if (scroller) scroller.dataset.menuOpen = "";
      opened.current = scroller;
      setFloatAt("inline");
      return;
    }
    const button = details.querySelector("summary").getBoundingClientRect();
    const height = details.querySelector(".ui-row-options").offsetHeight;
    const viewport = document.documentElement;
    const roomBelow = viewport.clientHeight - button.bottom;
    const above = roomBelow < height + GAP * 2 && button.top > height + GAP * 2;
    setFloatAt({
      position: "fixed",
      right: Math.max(GAP, viewport.clientWidth - button.right),
      left: "auto",
      ...(above
        ? { top: "auto", bottom: viewport.clientHeight - button.top + GAP }
        : { top: button.bottom + GAP, bottom: "auto" }),
    });
  }

  useEffect(() => () => {
    if (opened.current) delete opened.current.dataset.menuOpen;
  }, []);

  useEffect(() => {
    if (!floatAt || floatAt === "inline") return undefined;
    const close = (event) => {
      // Scrolling inside the menu itself is fine.
      if (event.type === "scroll" && menu.current?.contains(event.target)) return;
      menu.current?.removeAttribute("open");
      setFloatAt(null);
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [floatAt]);

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
        // Hidden (but measurable) until placed, so it never shows in the
        // wrong spot for a frame first.
        style={
          !inScroller || floatAt === "inline"
            ? undefined
            : (floatAt ?? { visibility: "hidden" })
        }
        onClick={closeAfterSelection}
      >
        {children}
      </div>
    </details>
  );
}
