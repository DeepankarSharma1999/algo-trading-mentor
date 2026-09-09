import { redirect } from "next/navigation";
import { register } from "@/app/actions/auth";
import { AuthForm } from "@/components/AuthForm";
import { currentUser } from "@/lib/auth";

export default async function RegisterPage() {
  if (await currentUser()) redirect("/desk");
  return <AuthForm action={register} mode="register" />;
}
