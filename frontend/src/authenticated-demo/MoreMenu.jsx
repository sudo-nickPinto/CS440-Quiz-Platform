import { useEffect, useRef, useState } from "react";

import "./more-menu.css";

// Matches .qb-more-menu's min-width plus a little room.
const MENU_WIDTH = 250;

// "More ▾": a few rare or risky actions (archive, move to trash) one click
// away from the everyday buttons, so they aren't pressed by accident.
//
//   <MoreMenu items={[{ label: "Archive…", onSelect: archive, danger: true }]} />
//
// Items with `hidden: true` are left out; the menu disappears when none
// are left.
export default function MoreMenu({ label = "More", items, disabled = false }) {
  const ref = useRef(null);
  // Opens to the right of the button unless that would leave the window.
  const [alignRight, setAlignRight] = useState(false);
  const shown = items.filter((item) => !item.hidden);

  useEffect(() => {
    function closeOutside(event) {
      const menu = ref.current;
      if (menu?.open && !menu.contains(event.target)) menu.open = false;
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  if (shown.length === 0) return null;

  function close() {
    if (ref.current) ref.current.open = false;
  }

  return (
    <details
      ref={ref}
      className="qb-more"
      onToggle={() => {
        const menu = ref.current;
        if (!menu?.open) return;
        const { left } = menu.getBoundingClientRect();
        setAlignRight(left + MENU_WIDTH > window.innerWidth);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && ref.current?.open) {
          close();
          ref.current.querySelector("summary")?.focus();
        }
      }}
    >
      <summary>
        {label} <span aria-hidden="true">▾</span>
      </summary>

      <div className={"qb-more-menu" + (alignRight ? " is-right" : "")}>
        {shown.map((item) => (
          <button
            key={item.label}
            type="button"
            className={"qb-more-item" + (item.danger ? " is-danger" : "")}
            disabled={disabled || item.disabled}
            onClick={() => {
              close();
              item.onSelect();
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </details>
  );
}
