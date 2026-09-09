import type { BehaviourState } from "@/lib/types";

const cls: Record<BehaviourState, string> = { CALM: "chip--calm", ELEVATED: "chip--elevated", COOLDOWN: "chip--cooldown", RESEARCH: "chip--research" };

/** Behavioural state chip. Shape encodes state (see DESIGN.md), not just colour. */
export function StateChip({ state, title }: { state: BehaviourState; title?: string }) {
  return <span className={`chip ${cls[state]}`} title={title} data-state={state}>{state}</span>;
}

export function PlainChip({ children }: { children: React.ReactNode }) {
  return <span className="chip chip--state-plain">{children}</span>;
}
