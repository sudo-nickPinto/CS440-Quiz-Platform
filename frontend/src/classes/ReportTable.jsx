import { Fragment, useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { useRemembered } from "../authenticated-demo/remember";
import { formatScore, opensRow, pluralNoun, rowLink } from "./classHelpers";

// Pieces of the class report tables, shared by the class page tabs and the
// quiz presentation history page (ClassReports.jsx).

// A searchable report table; `rows` are { key, text, cells, to? } where
// `text` is what the search box matches and `to`, if set, is opened by a
// click anywhere on the row (the row's own links stay the keyboard path).
// A row can instead open in place: `onToggle` runs on a row click, `open`
// marks it opened, and `after` is rendered right below it (more <tr>s).
export function ReportTable({
  caption,
  noun,
  headers,
  rows,
  pagination,
  onPageChange,
  emptyTitle,
  emptyText,
  emptyAction = null,
  controls = null,
  columnClasses = [],
  tableClass = "",
  rememberAs = null,
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useRemembered(
    rememberAs && `${rememberAs}:query`,
    "",
  );
  const needle = query.trim().toLowerCase();
  const visible = rows.filter((row) => row.text.toLowerCase().includes(needle));
  const totalItems = pagination?.total_items ?? rows.length;
  const page = pagination?.page ?? 1;
  const totalPages = pagination?.total_pages ?? (totalItems ? 1 : 0);
  const pageSize = pagination?.page_size ?? Math.max(rows.length, 1);
  const firstItem = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(firstItem + rows.length - 1, totalItems);
  const nounLabel = pluralNoun(totalItems, noun);

  // A remembered page can be past the end once rows are removed.
  const pastEnd = Boolean(onPageChange) && page > Math.max(totalPages, 1);
  useEffect(() => {
    if (pastEnd) onPageChange(Math.max(totalPages, 1));
  }, [pastEnd, totalPages, onPageChange]);

  return (
    <>
      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">
            Search this page of {caption.toLowerCase()}
          </span>
          <input
            type="search"
            placeholder={`Search this page of ${caption.toLowerCase()}…`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        {controls}

        <span className="cl-count" aria-live="polite">
          {needle
            ? `${visible.length} of ${rows.length} ${nounLabel} on this page`
            : totalItems === 0
              ? `0 ${nounLabel}`
              : `${firstItem}–${lastItem} of ${totalItems} ${nounLabel}`}
        </span>
      </div>

      <div className="cl-table-wrap">
        <table className={`cl-table ${tableClass}`.trim()}>
          <caption className="cl-sr">{caption}</caption>

          <thead>
            <tr>
              {headers.map((heading, index) => (
                <th
                  key={heading || index}
                  scope="col"
                  className={columnClasses[index] || undefined}
                >
                  {heading || <span className="cl-sr">Actions</span>}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={headers.length}>
                  <div className="cl-state" role="status">
                    <h2>{needle ? "No matches" : emptyTitle}</h2>
                    <p>{needle ? "Try another search." : emptyText}</p>
                    {!needle && emptyAction}
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((row) => (
                <Fragment key={row.key}>
                <tr
                  {...(row.to ? rowLink(navigate, row.to) : null)}
                  {...(row.onToggle
                    ? {
                        className: "cl-click-row cl-fold-row",
                        "data-open": Boolean(row.open),
                        onClick: (event) => {
                          if (
                            opensRow(
                              event,
                              globalThis.getSelection?.()?.toString() ?? "",
                            )
                          ) {
                            row.onToggle();
                          }
                        },
                      }
                    : null)}
                >
                  {row.cells.map((cell, index) => (
                    <td
                      key={headers[index] || index}
                      className={
                        [index === 0 ? row.leadClass : "", columnClasses[index]]
                          .filter(Boolean)
                          .join(" ") || undefined
                      }
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
                {row.after}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>

      {onPageChange && totalPages > 1 && (
        <nav className="cl-pagination" aria-label={`${caption} pages`}>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            ← Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next →
          </button>
        </nav>
      )}
    </>
  );
}

const MONTH = new Intl.DateTimeFormat(undefined, { month: "short" });

// The apricot date block that leads each presentation row.
export function DateBlock({ value }) {
  if (!value) return "—";
  const date = new Date(value);
  return (
    <span className="cl-date-block">
      <small>{MONTH.format(date)}</small>
      <b>{String(date.getDate()).padStart(2, "0")}</b>
    </span>
  );
}

// A navy bar for an average against the best score, with the number.
export function ScoreMeter({ value, max, label }) {
  const share =
    value === null || value === undefined || !max
      ? 0
      : Math.min(value / max, 1);
  return (
    <span className="cl-meter-cell">
      <span className="cl-meter" aria-hidden="true">
        <i style={{ width: `${Math.round(share * 100)}%` }} />
      </span>
      <b className="cl-meter-num" aria-label={label}>
        {formatScore(value == null ? value : Math.round(value))}
      </b>
    </span>
  );
}

export function Fraction({ value, total }) {
  return (
    <span className="cl-fraction">
      <b>{formatScore(value)}</b>
      {total ? <small> / {formatScore(total)}</small> : null}
    </span>
  );
}

export function GoLink({ to, label }) {
  return (
    <Link className="cl-go" to={to} aria-label={label} title={label}>
      →
    </Link>
  );
}
