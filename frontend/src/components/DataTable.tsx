import type { ReactNode } from "react";

export type DataTableAlign = "left" | "right";
export type DataTableAriaSort = "ascending" | "descending" | "none";

export interface DataTableColumn<T> {
  /** A stable, unique key for this column (React key and cell key prefix). */
  key: string;
  header: string;
  align?: DataTableAlign;
  /** Renders a `<button class="sort">` inside the header cell when true
   * (AC3, E3-S3); a plain, non-interactive header otherwise. */
  sortable?: boolean;
  /** When set, the header cell carries `aria-sort` with this value
   * (`"none"` included) -- for the active-sort columns and any column that
   * statically reflects sort state without being clickable itself. Columns
   * that never relate to sorting leave this `undefined` so no `aria-sort`
   * attribute is rendered on their header at all. */
  ariaSort?: DataTableAriaSort;
  onSort?: () => void;
  renderCell: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  /** Visually hidden `<caption>` content (row count, current sort) so
   * assistive technology always has that context, per AC4. */
  caption: ReactNode;
  /** Whole-row click, for mouse/pointer users. Never the only way to
   * activate a row -- a caller that needs keyboard/screen-reader
   * operability puts a real focusable element (e.g. a `Link`) in a cell's
   * `renderCell`, since a `<tr>` click handler alone is not keyboard
   * operable. */
  onRowClick?: (row: T) => void;
}

function alignClassName(align: DataTableAlign | undefined): string | undefined {
  return align === "right" ? "num" : undefined;
}

function SortButton<T>({ column }: { column: DataTableColumn<T> }): JSX.Element {
  const indicator = column.ariaSort === "ascending" ? "▲" : column.ariaSort === "descending" ? "▼" : "↕";
  return (
    <button type="button" className="sort" onClick={column.onSort}>
      {column.header}
      <span aria-hidden="true">{indicator}</span>
    </button>
  );
}

/**
 * Generic sortable, clickable-row table. Takes columns and rows, not any
 * particular domain shape -- Portfolio, Customer 360 and later screens all
 * reuse this rather than hand-rolling their own `<table>`.
 */
export function DataTable<T>({ columns, rows, getRowKey, caption, onRowClick }: DataTableProps<T>): JSX.Element {
  return (
    <div className="tablewrap">
      <table>
        <caption className="sr">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={alignClassName(column.align)}
                {...(column.ariaSort !== undefined ? { "aria-sort": column.ariaSort } : {})}
              >
                {column.sortable ? <SortButton column={column} /> : column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={getRowKey(row)}
              className={onRowClick ? "clickable" : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} className={alignClassName(column.align)}>
                  {column.renderCell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
