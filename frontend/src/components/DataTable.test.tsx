import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataTable, type DataTableColumn } from "./DataTable";

interface Product {
  id: string;
  name: string;
  price: number;
}

const PRODUCTS: Product[] = [
  { id: "p1", name: "Widget", price: 12 },
  { id: "p2", name: "Gadget", price: 30 },
];

function nameSortColumn(ariaSort: "ascending" | "descending" | "none", onSort: () => void): DataTableColumn<Product> {
  return {
    key: "name",
    header: "Name",
    sortable: true,
    ariaSort,
    onSort,
    renderCell: (row) => row.name,
  };
}

const PRICE_COLUMN: DataTableColumn<Product> = {
  key: "price",
  header: "Price",
  align: "right",
  renderCell: (row) => String(row.price),
};

describe("DataTable (generic, exercised with non-portfolio data)", () => {
  it("renders a header cell and a data cell for every configured column, in order", () => {
    render(
      <DataTable
        columns={[nameSortColumn("none", vi.fn()), PRICE_COLUMN]}
        rows={PRODUCTS}
        getRowKey={(row) => row.id}
        caption="Products, 2 rows."
      />,
    );
    const headers = screen.getAllByRole("columnheader").map((th) => th.textContent);
    expect(headers).toEqual(["Name↕", "Price"]);
    const firstRow = screen.getByText("Widget").closest("tr") as HTMLElement;
    expect(within(firstRow).getByText("12")).toBeInTheDocument();
  });

  it("renders a visually hidden caption with the given content", () => {
    render(
      <DataTable columns={[PRICE_COLUMN]} rows={PRODUCTS} getRowKey={(row) => row.id} caption="Products, 2 rows." />,
    );
    expect(screen.getByText("Products, 2 rows.")).toHaveClass("sr");
  });

  it("sets aria-sort only on columns that declare it, and omits it entirely for plain columns", () => {
    render(
      <DataTable
        columns={[nameSortColumn("ascending", vi.fn()), PRICE_COLUMN]}
        rows={PRODUCTS}
        getRowKey={(row) => row.id}
        caption="caption"
      />,
    );
    const [nameHeader, priceHeader] = screen.getAllByRole("columnheader");
    expect(nameHeader).toHaveAttribute("aria-sort", "ascending");
    expect(priceHeader).not.toHaveAttribute("aria-sort");
  });

  it("calls onSort when a sortable column's header button is activated by click", async () => {
    const onSort = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable
        columns={[nameSortColumn("none", onSort), PRICE_COLUMN]}
        rows={PRODUCTS}
        getRowKey={(row) => row.id}
        caption="caption"
      />,
    );
    await user.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it("is keyboard-operable: a sortable header button can be tabbed to and activated with Enter", async () => {
    const onSort = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable
        columns={[nameSortColumn("none", onSort)]}
        rows={PRODUCTS}
        getRowKey={(row) => row.id}
        caption="caption"
      />,
    );
    await user.tab();
    expect(screen.getByRole("button", { name: /Name/ })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it("calls onRowClick with the clicked row when rows are clickable", async () => {
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable columns={[PRICE_COLUMN]} rows={PRODUCTS} getRowKey={(row) => row.id} caption="caption" onRowClick={onRowClick} />,
    );
    await user.click(screen.getByText("30"));
    expect(onRowClick).toHaveBeenCalledWith(PRODUCTS[1]);
  });

  it("renders one row per item, keyed by getRowKey", () => {
    render(
      <DataTable columns={[PRICE_COLUMN]} rows={PRODUCTS} getRowKey={(row) => row.id} caption="caption" />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(3); // header row + 2 data rows
  });
});
