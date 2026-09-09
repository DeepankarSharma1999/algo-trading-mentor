import { redirect } from "next/navigation";
import { currentUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function Home() {
  const u = await currentUser();
  redirect(u ? (u.profile?.onboardedAt ? "/desk" : "/onboarding") : "/login");
}
