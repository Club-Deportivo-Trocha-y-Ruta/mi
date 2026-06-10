/**
 * Table — primitivo shadcn/ui para tablas de datos.
 *
 * Componentes exportados:
 *   - Table           → <table> con scroll horizontal en contenedor
 *   - TableHeader     → <thead>
 *   - TableBody       → <tbody>
 *   - TableFooter     → <tfoot>
 *   - TableRow        → <tr> con hover y estilos de selección
 *   - TableHead       → <th> — encabezado de columna
 *   - TableCell       → <td> — celda de datos
 *   - TableCaption    → <caption> — accesibilidad (descripción de la tabla)
 *
 * Accesibilidad:
 *   - Usa elementos HTML semánticos nativos (<table>, <thead>, <th scope>,
 *     <caption>) para que los lectores de pantalla naveguen correctamente.
 *   - Focus ring en TableRow cuando es interactivo.
 *
 * Patrón shadcn estándar — componente local, sin nueva dependencia.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Table wrapper (scroll horizontal en mobile)
// ---------------------------------------------------------------------------

const Table = React.forwardRef<
  HTMLTableElement,
  React.HTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
  <div className="relative w-full overflow-auto">
    <table
      ref={ref}
      className={cn("min-w-full caption-bottom text-sm", className)}
      {...props}
    />
  </div>
));
Table.displayName = "Table";

// ---------------------------------------------------------------------------
// TableHeader
// ---------------------------------------------------------------------------

const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead
    ref={ref}
    className={cn("[&_tr]:border-b", className)}
    {...props}
  />
));
TableHeader.displayName = "TableHeader";

// ---------------------------------------------------------------------------
// TableBody
// ---------------------------------------------------------------------------

const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0", className)}
    {...props}
  />
));
TableBody.displayName = "TableBody";

// ---------------------------------------------------------------------------
// TableFooter
// ---------------------------------------------------------------------------

const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn(
      "border-t bg-light-gray/50 font-medium [&>tr]:last:border-b-0",
      className,
    )}
    {...props}
  />
));
TableFooter.displayName = "TableFooter";

// ---------------------------------------------------------------------------
// TableRow
// ---------------------------------------------------------------------------

const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b transition-colors hover:bg-light-gray/50 data-[state=selected]:bg-light-gray",
      className,
    )}
    {...props}
  />
));
TableRow.displayName = "TableRow";

// ---------------------------------------------------------------------------
// TableHead (th)
// ---------------------------------------------------------------------------

const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn(
      "h-11 px-4 text-left align-middle text-[11px] font-medium uppercase tracking-wide text-mid-gray",
      "[&:has([role=checkbox])]:pr-0",
      className,
    )}
    {...props}
  />
));
TableHead.displayName = "TableHead";

// ---------------------------------------------------------------------------
// TableCell (td)
// ---------------------------------------------------------------------------

const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn(
      "px-4 py-3 align-middle text-sm text-charcoal [&:has([role=checkbox])]:pr-0",
      className,
    )}
    {...props}
  />
));
TableCell.displayName = "TableCell";

// ---------------------------------------------------------------------------
// TableCaption
// ---------------------------------------------------------------------------

const TableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  React.HTMLAttributes<HTMLTableCaptionElement>
>(({ className, ...props }, ref) => (
  <caption
    ref={ref}
    className={cn("mt-3 text-xs text-mid-gray", className)}
    {...props}
  />
));
TableCaption.displayName = "TableCaption";

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
};
