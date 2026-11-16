export type Stage = {
  name: string;
  latency_ms: number;
  llm_calls: number;
  model: string | null;
  tokens_in: number;
  tokens_out: number;
  cached_tokens: number;
  wait_ms: number;
};

export type Join = {
  from: string;
  from_columns: string[];
  to: string;
  to_columns: string[];
  inferred: boolean;
};

export type AskResponse = {
  request_id?: string | null;
  question: string;
  sql: string | null;
  columns: string[];
  rows: string[][];
  truncated: boolean;
  error: string | null;
  stages: Stage[];
  details: {
    candidates?: string[];
    joins?: Join[];
    columns?: Record<string, string[]>;
    selected?: string[];
    rung?: string;
    validation?: string | null;
    first_error?: string;
  };
};

export type Database = {
  db_id: string;
  tables: string[];
};
