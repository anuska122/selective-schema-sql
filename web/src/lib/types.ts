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

export type AskResponse = {
  question: string;
  sql: string | null;
  columns: string[];
  rows: string[][];
  truncated: boolean;
  error: string | null;
  stages: Stage[];
  details: {
    candidates?: string[];
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
