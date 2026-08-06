export function updateReview<T extends { human_review: object }>(pack: T, review: Partial<T["human_review"]>): T;
export function selectCandidate<T extends { pack_id: string }>(candidate: { pack_id: string }, packs: Map<string, T>): { kind: string; [key: string]: unknown };
export function mayGenerate(state: unknown): boolean;
