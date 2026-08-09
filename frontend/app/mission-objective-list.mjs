/* eslint-disable react/prop-types */

import { createElement } from "react";

const rolePresentation = {
  prerequisite: { label: "Prerequisite", className: "is-prerequisite" },
  primary: { label: "Required", className: "is-required" },
  support: { label: "Required support", className: "is-support" },
  bonus: { label: "Bonus", className: "is-bonus" },
  completion: { label: "Completion", className: "is-completion" },
};

export function missionObjectiveRoleLabel(objectiveRole) {
  return rolePresentation[objectiveRole]?.label ?? "Required";
}

export function MissionObjectiveList({
  objectives,
  variant = "mission",
  ariaLabel = "Next Chapter mission steps",
}) {
  const listClassName = variant === "memory" ? "player-objectives" : "mission-objective-list";
  return createElement(
    "ol",
    { className: listClassName, "aria-label": ariaLabel },
    objectives.map((objective, index) => {
      const presentation = rolePresentation[objective.objective_role] ?? rolePresentation.primary;
      return createElement(
        "li",
        {
          className: `mission-objective ${presentation.className}`,
          "data-objective-role": objective.objective_role,
          key: objective.objective_ref,
        },
        createElement("span", { className: "mission-objective-number", "aria-hidden": "true" }, index + 1),
        createElement(
          "div",
          { className: "mission-objective-copy" },
          createElement("small", { className: "mission-objective-role" }, presentation.label),
          createElement("p", null, objective.description),
        ),
      );
    }),
  );
}
