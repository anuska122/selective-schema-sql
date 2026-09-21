type Props = {
  columns: string[];
  rows: string[][];
  truncated: boolean;
};

export function ResultsTable({ columns, rows, truncated }: Props) {
  if (rows.length === 0) {
    return <p className="text-sm text-stone-500">The query returned no rows.</p>;
  }
  if (rows.length === 1 && columns.length === 1) {
    return (
      <div className="flex animate-pop flex-col gap-1">
        <span className="font-serif text-6xl text-stone-900 tabular-nums dark:text-stone-50">{rows[0][0]}</span>
        <span className="font-mono text-xs text-stone-500">{columns[0]}</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="max-h-96 overflow-auto rounded-xl ring-1 ring-stone-200 dark:ring-stone-700">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-stone-50 dark:bg-stone-800">
            <tr>
              {columns.map((column) => (
                <th key={column} className="whitespace-nowrap px-4 py-2.5 text-xs font-semibold text-stone-600 dark:text-stone-300">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-stone-50 dark:hover:bg-stone-800/50">
                {row.map((value, j) => (
                  <td key={j} className="whitespace-nowrap px-4 py-2 tabular-nums text-stone-800 dark:text-stone-200">
                    {value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && <p className="text-xs text-stone-500">Showing the first {rows.length} rows.</p>}
    </div>
  );
}
