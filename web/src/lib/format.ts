export function databaseName(dbId: string): string {
  if (!dbId) return "All tables";
  const words = dbId.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
