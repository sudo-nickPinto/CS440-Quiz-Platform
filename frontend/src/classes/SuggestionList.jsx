// The scrolling people list in "+ Add student" and "Add collaborator":
// about four people show, and scrolling near the bottom loads the next page.
// `suggestions` comes from useSuggestions; `renderPerson` draws one <li>.
export default function SuggestionList({ id, label, suggestions, renderPerson, emptyText }) {
  const { items, hasMore, loading, loadMore } = suggestions;

  function loadMoreNearBottom(event) {
    const box = event.currentTarget;
    if (box.scrollTop + box.clientHeight >= box.scrollHeight - 60) void loadMore();
  }

  return (
    <div className="cl-suggest-box" onScroll={loadMoreNearBottom} aria-busy={loading}>
      {items.length > 0 && (
        <ul className="cl-suggest" id={id} role="listbox" aria-label={label}>
          {items.map(renderPerson)}
        </ul>
      )}
      {items.length === 0 ? (
        <p className="cl-suggest-note" role="status">
          {loading ? "Loading people…" : emptyText}
        </p>
      ) : hasMore ? (
        <p className="cl-suggest-note" aria-hidden="true">Loading more…</p>
      ) : null}
    </div>
  );
}
