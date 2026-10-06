import dictionary from "../../api/skill_dictionary.json";

const escapePattern = (term: string) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const patterns = Object.entries(dictionary).map(([skill, aliases]) => ({
  skill,
  pattern: new RegExp(`(?:^|[^a-z0-9_+#])(?:${[skill, ...aliases].map(escapePattern).join("|")})(?![a-z0-9_+#])`, "i"),
}));

// These are literal mentions. The user reviews whether they represent skills used.
export function detectSkills(text: string): string[] {
  return patterns.filter(({ pattern }) => pattern.test(text)).map(({ skill }) => skill);
}
