"use server";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { cloneTemplate } from "@/lib/strategies";

/** Clone a template into the user's own strategies and open it in the Builder. */
export async function cloneAction(form: FormData) {
  const user = await requireUser();
  const templateId = String(form.get("template_id") ?? "");
  let id: string;
  try {
    id = await cloneTemplate(user.id, templateId);
  } catch {
    redirect("/library?notice=" + encodeURIComponent("That template could not be cloned. Reload the Library and try again."));
  }
  redirect(`/builder/${id}`);
}
