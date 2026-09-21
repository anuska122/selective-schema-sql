type Props = {
  columns: string[];
  rows: string[][];
  truncated: boolean;
};

export function ResultsTable({ columns, rows, truncated }: Props) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">The query returned no rows.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-zinc-50">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2 font-medium text-zinc-700">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-zinc-100">
              {row.map((value, j) => (
                <td key={j} className="px-3 py-1.5 font-mono text-xs">
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && <p className="px-3 py-2 text-xs text-zinc-500">Showing the first {rows.length} rows.</p>}
    </div>
  );
}
