"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const SECTIONS = [
  ["/desk", "desk"],
  ["/library", "library"],
  ["/builder", "builder"],
  ["/validation", "validation"],
  ["/journal", "journal"],
  ["/research", "research"],
  ["/settings", "settings"],
] as const;

export function Rail({ email, researchAllowed }: { email: string; researchAllowed: boolean }) {
  const path = usePathname();
  return (
    <nav className="rail" aria-label="Sections">
      <div className="rail__brand">Algo Trading Mentor</div>
      <ul className="rail__list">
        {SECTIONS.map(([href, label]) => {
          const current = path === href || path.startsWith(href + "/");
          const locked = href === "/research" && !researchAllowed;
          return (
            <li className="rail__item" key={href}>
              <Link href={href} aria-current={current ? "page" : undefined} title={locked ? "Research opens when your state is RESEARCH (market closed)." : undefined} className={locked ? "faint" : undefined}>
                {label}{locked ? " ·" : ""}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="rail__foot">
        <div className="mono" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{email}</div>
        <form action="/api/logout" method="post"><button className="btn btn--sm" style={{ marginTop: 8 }}>Sign out</button></form>
      </div>
    </nav>
  );
}
