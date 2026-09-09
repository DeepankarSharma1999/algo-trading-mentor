import { redirect } from "next/navigation";
import { destroySession } from "@/lib/auth";

export async function POST() {
  await destroySession();
  redirect("/login");
}
