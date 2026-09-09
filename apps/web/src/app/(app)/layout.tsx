import { Footer } from "@/components/Footer";
import { Rail } from "@/components/Rail";
import { Strip } from "@/components/Strip";
import { requireUser } from "@/lib/auth";
import { stripData } from "@/lib/strip";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await requireUser();
  const strip = await stripData(user.id);
  return (
    <div className="frame">
      <Rail email={user.email} researchAllowed={strip.state === "RESEARCH"} />
      <div className="main">
        <Strip d={strip} />
        <div className="content">{children}</div>
        <Footer provider={strip.provider} />
      </div>
    </div>
  );
}
