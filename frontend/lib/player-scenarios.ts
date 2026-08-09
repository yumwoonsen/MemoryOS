export const playerExperienceRefs = [
  "memory-01",
  "memory-02",
  "memory-03",
  "memory-04",
] as const;

export type PlayerExperienceRef = (typeof playerExperienceRefs)[number];

export type PlayerExperienceDescriptor = {
  experience_ref: PlayerExperienceRef;
  label: string;
  teaser: string;
};

export const playerExperiences: readonly PlayerExperienceDescriptor[] = [
  {
    experience_ref: "memory-01",
    label: "Rescue at Clock Tower",
    teaser: "A connected rescue and escape from Clock Tower.",
  },
  {
    experience_ref: "memory-02",
    label: "Peak landing",
    teaser: "A shared named landing at Peak.",
  },
  {
    experience_ref: "memory-03",
    label: "Katulistiwa assist",
    teaser: "A linked assist and elimination at Katulistiwa.",
  },
  {
    experience_ref: "memory-04",
    label: "Observatory near misses",
    teaser: "Repeated close finishes from the same squad.",
  },
] as const;

export function isPlayerExperienceRef(value: unknown): value is PlayerExperienceRef {
  return typeof value === "string"
    && playerExperienceRefs.includes(value as PlayerExperienceRef);
}

export function playerExperienceDescriptor(experienceRef: PlayerExperienceRef) {
  return playerExperiences.find((experience) => experience.experience_ref === experienceRef)!;
}
