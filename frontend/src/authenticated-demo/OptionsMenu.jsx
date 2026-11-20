import { useRef } from "react";

// Native <details> keeps this small and keyboard accessible. Selecting any
// action closes the popover so it behaves like a conventional options menu.
export default function OptionsMenu({ children, className = "" }) {
  const menu = useRef(null);

  function closeAfterSelection(event) {
    if (event.target.closest("a, button")) {
      menu.current?.removeAttribute("open");
    }
  }

  return (
    <details ref={menu} className={`ui-row-menu ${className}`.trim()}>
      <summary aria-label="Options" title="Options">
        <span aria-hidden="true">⋯</span>
      </summary>
      <div className="ui-row-options" onClick={closeAfterSelection}>
        {children}
      </div>
    </details>
  );
}
