"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export const SECTIONS = [
  ["/desk", "Desk", "Live watchers and the latest rule trace"],
  ["/library", "Library", "Templates to learn the schema"],
  ["/builder", "Builder", "Write and edit your rule sets"],
  ["/validation", "Validation", "The eight-stage test of a strategy"],
  ["/journal", "Journal", "Closed paper trades and process scores"],
  ["/research", "Research", "Change parameters when the market is closed"],
  ["/settings", "Settings", "Buckets, profile, costs, clock, theme"],
  ["/help", "Help", "What every term on screen means"],
] as const;

const isCurrent = (path: string, href: string) => path === href || path.startsWith(href + "/");

export function Rail({ email, researchAllowed }: { email: string; researchAllowed: boolean }) {
  const path = usePathname();
  return (
    <nav className="rail" aria-label="Sections">
      <div className="rail__brand">Algo Trading Mentor</div>
      <ul className="rail__list">
        {SECTIONS.map(([href, label, hint]) => {
          const locked = href === "/research" && !researchAllowed;
          return (
            <li className="rail__item" key={href}>
              <Link href={href} aria-current={isCurrent(path, href) ? "page" : undefined} title={locked ? "Research opens when your state is RESEARCH (market closed). You can still read version history." : hint}>
                <span>{label}{locked ? " (read-only)" : ""}</span>
                <small>{hint}</small>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="rail__foot">
        <div className="mono" style={{ overflow: "hidden", textOverflow: "ellipsis" }} title={email}>{email}</div>
        <form action="/api/logout" method="post"><button className="btn btn--sm" style={{ marginTop: 8 }}>Sign out</button></form>
      </div>
    </nav>
  );
}

/** Narrow-screen navigation; hidden on desktop by CSS. */
export function TopNav() {
  const path = usePathname();
  return (
    <nav className="topnav" aria-label="Sections">
      {SECTIONS.map(([href, label]) => (
        <Link key={href} href={href} aria-current={isCurrent(path, href) ? "page" : undefined}>{label}</Link>
      ))}
    </nav>
  );
}
